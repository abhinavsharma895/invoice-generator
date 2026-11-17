import re
from io import BytesIO
from datetime import date
import streamlit as st
import database

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
# ---------------- CONFIGURATION ----------------
st.set_page_config(
    page_title="Invoice Generator",
    layout="wide",
)
database.initialize_database()

RESTAURANT_NAME = "ABC Restaurant"
RESTAURANT_GSTIN = "27AAAPA1234A1Z5"
USER_ID = 1
GST_RATE = 5

# ---------------- SESSION STATE ----------------
defaults = {
    "cart": {},
    "show_cart": False,
    "customer_name_saved": "",
    "customer_gstin_saved": "",
    "saved_invoice_message": None,
    "save_error": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Widget keys are dropped by Streamlit when the widget is not shown
# (e.g. on the Order History page), so restore them from the saved copy.
if "customer_name_input" not in st.session_state:
    st.session_state.customer_name_input = st.session_state.customer_name_saved

if "customer_gstin_input" not in st.session_state:
    st.session_state.customer_gstin_input = st.session_state.customer_gstin_saved
# ---------------- HELPERS ----------------

def save_customer_name():
    st.session_state.customer_name_saved = st.session_state.customer_name_input


def save_customer_gstin():
    st.session_state.customer_gstin_saved = st.session_state.customer_gstin_input


def validate_gstin(gstin):
    pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]$"
    return bool(re.fullmatch(pattern, gstin))


def add_to_cart(item, quantity):
    item_id, item_name, category, price = item

    if item_id in st.session_state.cart:
        st.session_state.cart[item_id]["quantity"] += quantity
    else:
        st.session_state.cart[item_id] = {
            "item_id": item_id,
            "item_name": item_name,
            "category": category,
            "price": price,
            "quantity": quantity,
        }

    cart_item = st.session_state.cart[item_id]
    cart_item["total"] = cart_item["price"] * cart_item["quantity"]

    # Keep the cart-screen quantity widget in sync
    st.session_state.pop(f"cart_quantity_{item_id}", None)


def remove_from_cart(item_id):
    st.session_state.cart.pop(item_id, None)
    st.session_state.pop(f"cart_quantity_{item_id}", None)


def update_quantity(item_id):
    quantity = st.session_state[f"cart_quantity_{item_id}"]

    if item_id in st.session_state.cart:
        item = st.session_state.cart[item_id]
        item["quantity"] = quantity
        item["total"] = item["price"] * quantity


def get_subtotal():
    return sum(item["total"] for item in st.session_state.cart.values())


def calculate_bill(discount_percent):
    subtotal = get_subtotal()
    discount = round(subtotal * discount_percent / 100, 2)
    taxable = subtotal - discount
    gst = round(taxable * GST_RATE / 100, 2)
    grand_total = round(taxable + gst, 2)
    return subtotal, discount, gst, grand_total


def generate_invoice_pdf(
    invoice_id, order_id, invoice_date, customer_name, customer_gstin,
    items, subtotal, discount, gst, grand_total
):
    """Create a downloadable PDF invoice and return its bytes."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "InvoiceTitle", parent=styles["Title"], fontSize=20,
        textColor=colors.HexColor("#183153"), spaceAfter=8
    )
    story = [
        Paragraph("TAX INVOICE", title_style),
        Paragraph(f"<b>{RESTAURANT_NAME}</b>", styles["Heading2"]),
        Paragraph(f"Restaurant GSTIN: {RESTAURANT_GSTIN or 'Not Provided'}", styles["Normal"]),
        Spacer(1, 10),
    ]

    details = [
        ["Invoice ID", str(invoice_id), "Order ID", str(order_id)],
        ["Date", str(invoice_date), "Customer", str(customer_name)],
        ["Customer GSTIN", str(customer_gstin or "Not Provided"), "", ""],
    ]
    details_table = Table(details, colWidths=[28*mm, 58*mm, 25*mm, 58*mm])
    details_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F5F9")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5DDE7")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("PADDING", (0, 0), (-1, -1), 7),
        ("SPAN", (1, 2), (3, 2)),
    ]))
    story.extend([details_table, Spacer(1, 14)])

    table_rows = [["Item ID", "Food Item", "Price (INR)", "Qty", "Total (INR)"]]
    for item in items:
        # Supports both the cart dictionary and database.get_order_items tuple.
        if isinstance(item, dict):
            item_id = item.get("item_id", "")
            item_name = item.get("item_name", "")
            price = float(item.get("price", 0))
            quantity = int(item.get("quantity", 0))
            total = float(item.get("total", price * quantity))
        else:
            item_id, item_name, price, quantity, total = item
        table_rows.append([
            str(item_id), str(item_name), f"{float(price):.2f}",
            str(quantity), f"{float(total):.2f}"
        ])

    items_table = Table(
        table_rows, repeatRows=1,
        colWidths=[20*mm, 75*mm, 30*mm, 18*mm, 30*mm]
    )
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183153")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5DDE7")),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("PADDING", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
    ]))
    story.extend([items_table, Spacer(1, 12)])

    totals = [
        ["Subtotal", f"INR {float(subtotal):.2f}"],
        ["Discount", f"INR {float(discount):.2f}"],
        [f"GST ({GST_RATE}%)", f"INR {float(gst):.2f}"],
        ["Grand Total", f"INR {float(grand_total):.2f}"],
    ]
    totals_table = Table(totals, colWidths=[125*mm, 48*mm], hAlign="RIGHT")
    totals_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
        ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#E8EEF6")),
        ("LINEABOVE", (0, 3), (-1, 3), 0.8, colors.HexColor("#183153")),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([totals_table, Spacer(1, 18), Paragraph("Thank you for your order!", styles["Italic"])])

    doc.build(story)
    return buffer.getvalue()
# ---------------- SAVE INVOICE (button callback) ----------------

def save_invoice():
    """Runs as an on_click callback, before the page reruns.
    Errors are stored in session state and shown on the page."""

    st.session_state.save_error = None

    customer_name = st.session_state.get("customer_name_input", "").strip()
    customer_gstin = st.session_state.get("customer_gstin_input", "").strip().upper()

    if not customer_name:
        st.session_state.save_error = "Please enter the customer name."
        return

    if customer_gstin and not validate_gstin(customer_gstin):
        st.session_state.save_error = "Please enter a valid customer GSTIN."
        return

    if RESTAURANT_GSTIN and not validate_gstin(RESTAURANT_GSTIN):
        st.session_state.save_error = "Restaurant GSTIN is invalid."
        return

    if not st.session_state.cart:
        st.session_state.save_error = "Your cart is empty."
        return

    discount_percent = st.session_state.get("discount", 0.0)
    subtotal, discount, gst, grand_total = calculate_bill(discount_percent)

    try:
        order_id, invoice_id = database.save_order(
            user_id=USER_ID,
            cart=list(st.session_state.cart.values()),
            subtotal=subtotal,
            discount=discount,
            gst=gst,
            grand_total=grand_total,
            customer_name=customer_name,
            customer_gstin=customer_gstin,
        )
    except Exception as e:
        st.session_state.save_error = f"Unable to save invoice: {e}"
        return

    # Success: reset everything for the next customer
    st.session_state.saved_invoice_message = (order_id, invoice_id)
    st.session_state.cart = {}
    st.session_state.show_cart = False
    st.session_state.customer_name_saved = ""
    st.session_state.customer_gstin_saved = ""
    st.session_state.customer_name_input = ""
    st.session_state.customer_gstin_input = ""
    st.session_state.discount = 0.0


def toggle_cart():
    st.session_state.show_cart = not st.session_state.show_cart


def close_cart():
    st.session_state.show_cart = False


def dismiss_message():
    st.session_state.saved_invoice_message = None
# ---------------- HEADER ----------------

st.title("🍽️ Restaurant Invoice Generator")
st.caption("Search food items, manage your cart and generate invoices.")
st.divider()
# ---------------- SUCCESS MESSAGE ----------------

if st.session_state.saved_invoice_message:
    order_id, invoice_id = st.session_state.saved_invoice_message

    st.success("Invoice saved successfully!")
    st.write(f"**Order ID:** {order_id}")
    st.write(f"**Invoice ID:** {invoice_id}")
    st.button("Dismiss Message", on_click=dismiss_message)
    st.divider()
# ---------------- SIDEBAR ----------------

# ---------------- SIDEBAR ----------------

st.sidebar.title("Restaurant")

page = st.sidebar.radio(
    "Navigation",
    ["Create Invoice", "Order History"],
    key="navigation"
)

st.sidebar.divider()

cart_count = sum(
    item["quantity"] for item in st.session_state.cart.values()
)

st.sidebar.metric("Cart Items", cart_count)

if page == "Create Invoice":
    st.sidebar.button(
        "🛒 View Cart",
        use_container_width=True,
        on_click=toggle_cart
    )
# CREATE INVOICE PAGE
if page == "Create Invoice":

    # Customer details are shown on BOTH screens so the name is never lost
    st.subheader("Customer Details")

    col1, col2 = st.columns(2)
    with col1:
        st.text_input(
            "Customer Name",
            key="customer_name_input",
            on_change=save_customer_name,
        )
    with col2:
        st.text_input(
            "Customer GSTIN (Optional)",
            key="customer_gstin_input",
            on_change=save_customer_gstin,
        )

    st.divider()
    # ---------------- SEARCH SCREEN ----------------

    if not st.session_state.show_cart:

        st.subheader("Restaurant Details")

        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Restaurant:** {RESTAURANT_NAME}")
        with col2:
            st.write(f"**Restaurant GSTIN:** {RESTAURANT_GSTIN or 'Not Provided'}")

        st.divider()

        st.subheader("🔍 Search Food Items")

        menu_items = database.get_menu_items()

        search_query = st.text_input(
            "Search by Food Name or Food Item ID",
            placeholder="Type Burger, Pizza, 1 or all...",
        ).strip().lower()

        if search_query == "all":
            filtered_items = menu_items
        elif search_query:
            filtered_items = [
                item for item in menu_items
                if search_query in item[1].lower() or search_query == str(item[0])
            ]
        else:
            filtered_items = []

        if filtered_items:
            item_options = {
                f"ID: {item[0]} | {item[1]} | {item[2]} | ₹{item[3]:.2f}": item
                for item in filtered_items
            }

            selected_label = st.selectbox("Select Food Item", list(item_options.keys()))
            selected_item = item_options[selected_label]

            col1, col2 = st.columns(2)

            with col1:
                st.write(f"**Food Item:** {selected_item[1]}")
                st.write(f"**Category:** {selected_item[2]}")
                st.write(f"**Price:** ₹{selected_item[3]:.2f}")

            with col2:
                quantity = st.number_input(
                    "Quantity", min_value=1, max_value=100, value=1, step=1
                )

            if st.button("➕ Add to Cart", type="primary"):
                add_to_cart(selected_item, quantity)
                st.success(f"{selected_item[1]} added to cart!")

        elif search_query:
            st.warning("No food item found.")
        else:
            st.info("Search for a food item or type 'all' to see all items.")

        if st.session_state.cart:
            st.divider()
            st.subheader("Cart Summary")

            for item in st.session_state.cart.values():
                st.write(f"{item['item_name']} × {item['quantity']} — ₹{item['total']:.2f}")

            st.write(f"**Subtotal: ₹{get_subtotal():.2f}**")
            st.info("Click View Cart to open the invoice preview.")
# ---------------- INVOICE PREVIEW ----------------

    else:
        st.header("🧾 Invoice Preview")

        if st.session_state.save_error:
            st.error(st.session_state.save_error)

        if st.session_state.cart:

            st.subheader("Selected Food Items")

            invoice_data = [
                {
                    "Food Item ID": item["item_id"],
                    "Food Item": item["item_name"],
                    "Price": f"₹{item['price']:.2f}",
                    "Quantity": item["quantity"],
                    "Total": f"₹{item['total']:.2f}",
                }
                for item in st.session_state.cart.values()
            ]

            st.dataframe(invoice_data, use_container_width=True, hide_index=True)

            st.divider()
# ---------------- MANAGE CART ----------------

            st.subheader("Manage Cart")

            for item_id, item in list(st.session_state.cart.items()):
                col1, col2, col3 = st.columns([3, 2, 1])

                with col1:
                    st.write(f"**{item['item_name']}**")
                    st.caption(f"Item ID: {item_id}")

                with col2:
                    st.number_input(
                        "Quantity",
                        min_value=1,
                        max_value=100,
                        value=item["quantity"],
                        key=f"cart_quantity_{item_id}",
                        on_change=update_quantity,
                        args=(item_id,),
                    )

                with col3:
                    if st.button("Remove", key=f"remove_{item_id}"):
                        remove_from_cart(item_id)
                        st.rerun()

            st.divider()
# ---------------- BILL ----------------

            discount_percent = st.number_input(
                "Discount (%)",
                min_value=0.0,
                max_value=100.0,
                value=0.0,
                step=1.0,
                key="discount",
            )

            subtotal, discount, gst, grand_total = calculate_bill(discount_percent)

            st.divider()

            col1, col2 = st.columns(2)

            with col1:
                st.write(f"Subtotal: ₹{subtotal:.2f}")
                st.write(f"Discount: ₹{discount:.2f}")
                st.write(f"GST ({GST_RATE}%): ₹{gst:.2f}")

            with col2:
                st.metric("Grand Total", f"₹{grand_total:.2f}")

            draft_pdf = generate_invoice_pdf(
                invoice_id="DRAFT",
                order_id="Not saved",
                invoice_date=date.today().isoformat(),
                customer_name=st.session_state.get("customer_name_input", ""),
                customer_gstin=st.session_state.get("customer_gstin_input", ""),
                items=list(st.session_state.cart.values()),
                subtotal=subtotal,
                discount=discount,
                gst=gst,
                grand_total=grand_total,
            )
            st.download_button(
                "⬇️ Download Invoice PDF",
                data=draft_pdf,
                file_name="draft_invoice.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

            st.divider()

            col1, col2 = st.columns(2)

            with col1:
                st.button(
                    "Continue Shopping",
                    use_container_width=True,
                    on_click=close_cart,
                )

            with col2:
                st.button(
                    "Save Invoice",
                    type="primary",
                    use_container_width=True,
                    on_click=save_invoice,
                )

        else:
            st.info("Your cart is empty. Search for food items and add them.")
            st.button("Continue Shopping", on_click=close_cart)
# ORDER HISTORY PAGE

else:

    st.subheader("📋 Order History")

    try:
        orders = database.get_user_orders(USER_ID)

        if orders:

            history_data = [
                {
                    "Order ID": order[0],
                    "Invoice ID": order[1],
                    "Customer": order[2],
                    "Customer GSTIN": order[3] or "Not Provided",
                    "Subtotal": f"₹{order[4]:.2f}",
                    "Discount": f"₹{order[5]:.2f}",
                    "GST": f"₹{order[6]:.2f}",
                    "Grand Total": f"₹{order[7]:.2f}",
                    "Date": order[8],
                }
                for order in orders
            ]

            st.dataframe(history_data, use_container_width=True, hide_index=True)

            st.divider()

            st.subheader("View Saved Invoice")

            invoice_options = {f"{order[1]} - {order[2]}": order[1] for order in orders}

            selected_label = st.selectbox("Select Invoice", list(invoice_options.keys()))
            invoice = database.get_invoice_details(invoice_options[selected_label])

            if invoice:
                (
                    order_id,
                    invoice_id,
                    user_id,
                    customer_name,
                    customer_gstin,
                    subtotal,
                    discount,
                    gst,
                    grand_total,
                    order_date,
                ) = invoice

                st.divider()
                st.header("Saved Invoice")

                st.write(f"**Invoice ID:** {invoice_id}")
                st.write(f"**Order ID:** {order_id}")
                st.write(f"**Date:** {order_date}")

                st.divider()
                col1,col2=st.columns(2)
                with col1:
                    st.write(f"**Customer Name:** {customer_name}")
                    st.write(f"**Customer GSTIN:** {customer_gstin or 'Not Provided'}")
                with col2:
                    st.write(f"**Restaurant Name:** {RESTAURANT_NAME}")
                    st.write(f"**Restaurant GSTIN:** {RESTAURANT_GSTIN or 'Not Provided'}")
                
                invoice_items = database.get_order_items(order_id)

                item_data = [
                    {
                        "Food Item ID": item[0],
                        "Food Item": item[1],
                        "Price": f"₹{item[2]:.2f}",
                        "Quantity": item[3],
                        "Total": f"₹{item[4]:.2f}",
                    }
                    for item in invoice_items
                ]

                st.dataframe(item_data, use_container_width=True, hide_index=True)

                saved_pdf = generate_invoice_pdf(
                    invoice_id=invoice_id,
                    order_id=order_id,
                    invoice_date=order_date,
                    customer_name=customer_name,
                    customer_gstin=customer_gstin,
                    items=invoice_items,
                    subtotal=subtotal,
                    discount=discount,
                    gst=gst,
                    grand_total=grand_total,
                )
                safe_invoice_name = re.sub(r"[^A-Za-z0-9_-]", "_", str(invoice_id))
                st.download_button(
                    "⬇️ Download Saved Invoice PDF",
                    data=saved_pdf,
                    file_name=f"invoice_{safe_invoice_name}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

                st.divider()

                st.write(f"**Subtotal:** ₹{subtotal:.2f}")
                st.write(f"**Discount:** ₹{discount:.2f}")
                st.write(f"**GST:** ₹{gst:.2f}")
                st.subheader(f"Grand Total: ₹{grand_total:.2f}")

            else:
                st.warning("Invoice details not found.")

        else:
            st.info("No orders found. Create your first invoice.")

    except Exception as e:
        st.error(f"Unable to load order history: {e}")