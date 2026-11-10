"""Screen specifications for the NeuroGenUI sketch dataset.

Each screen is a small component tree. make_sketches.py lays it out, renders it in a
hand-drawn style and derives the ground-truth labels from the same tree, so the labels
are exact by construction.

Leaf helpers return dicts with key "t" = contract component type. Layout-only helpers
(ROW, COL, SP) are not components and never appear in the labels.
"""

# ---------------------------------------------------------------- helpers

def H(t, lvl=1, align="left"):
    return dict(t="heading", label=t, level=lvl, align=align)


def TX(t, align="left"):
    return dict(t="text", label=t, align=align)


def P(lines=2, w=1.0, align="left"):
    """Paragraph drawn as scribbles (unreadable text)."""
    return dict(t="text", label="", scribble=lines, wfrac=w, align=align)


def I(label, kind="text", w=None, align="left"):
    return dict(t="input", label=label, kind=kind, w=w, align=align)


def TA(label, rows=3):
    return dict(t="textarea", label=label, rows=rows)


def B(label, w=None, align="left", style="plain"):
    return dict(t="button", label=label, w=w, align=align, style=style)


def L(t, align="left"):
    return dict(t="link", label=t, align=align)


def CB(t, toggle=False):
    return dict(t="checkbox", label=t, toggle=toggle)


def RB(t):
    return dict(t="radio", label=t)


def SEL(t, w=None, options=None):
    return dict(t="select", label=t, w=w, options=options or [])


def IMG(h=160, w=None, align="left", glyph="x", shape="rect", alt=""):
    return dict(t="image", label="", h=h, w=w, align=align, glyph=glyph, shape=shape, alt=alt)


def DIV():
    return dict(t="divider", label="")


def ICO(glyph="circle", align="left", alt=""):
    return dict(t="icon", label="", glyph=glyph, align=align, alt=alt)


def NI(t):
    return dict(t="nav_item", label=t)


def LST(items):
    return dict(t="list", label="", items=items)


def NAV(left=(), right=(), vertical=False, items=()):
    """Navbar. Horizontal: `left` packed at the start, `right` packed at the end.
    Vertical (sidebar): `items` stacked."""
    return dict(t="navbar", label="", left=list(left), right=list(right),
                vertical=vertical, children=list(items))


def HDR(*ch, gap=20):
    return dict(t="header", label="", children=list(ch), dir="row", gap=gap)


def CARD(*ch, dir="col", gap=14, minh=0):
    return dict(t="card", label="", children=list(ch), dir=dir, gap=gap, minh=minh)


def FORM(*ch, gap=14):
    return dict(t="form", label="", children=list(ch), dir="col", gap=gap)


def BOX(*ch, dir="col", gap=14):
    return dict(t="container", label="", children=list(ch), dir=dir, gap=gap)


def ROW(*ch, weights=None, gap=24, valign="top"):
    return dict(t="_row", children=list(ch), weights=weights, gap=gap, valign=valign)


def COL(*ch, gap=16):
    return dict(t="_col", children=list(ch), gap=gap)


def SP(h=10):
    return dict(t="_sp", h=h)


def click(label, **expect):
    return {"event": "click", "target_label": label, "expect": expect}


# layout modes: content column width + left offset are derived in make_sketches.py
MOBILE, NARROW, DESKTOP = "mobile", "narrow", "desktop"

SCREENS = []


def screen(id, category, title, mode, root, instruction, interactions=()):
    SCREENS.append(dict(id=id, category=category, title=title, mode=mode, root=root,
                        instruction=instruction, interactions=list(interactions)))


# ---------------------------------------------------------------- login
screen("login_01", "login", "Login", MOBILE,
       COL(H("Login", 1, "center"), IMG(150, 0.5, "center", glyph="x", alt="logo"),
           I("Email", "email"), I("Password", "password"), B("Login", "full"), gap=22),
       "Create a login page with email and password fields and a login button.")

screen("login_02", "login", "Friendly login", DESKTOP,
       COL(HDR(H("Friendly", 2), I("Email", "email", 230), I("Password", "password", 230),
               B("Log In"), gap=22),
           SP(20), H("Connect with friends", 2), P(3, 0.7),
           IMG(230, "full", glyph="mountain", alt="banner"), gap=18),
       "A social network home page. The top bar has the Friendly logo text, an email field, a "
       "password field and a Log In button. Below it a big heading 'Connect with friends', a "
       "short paragraph and a wide banner image. Clicking Log In with empty fields shows an error.",
       [click("Log In", type="validate_required")])

screen("login_03", "login", "Welcome back", MOBILE,
       CARD(ICO("user", "center"), H("Welcome back", 2, "center"), I("Username"),
            I("Password", "password"),
            ROW(CB("Remember me"), L("Forgot password?", "right"), weights=[1, 1]),
            B("Sign in", "full"), DIV(), B("Continue with Google", "full", style="double"),
            L("Create an account", "center"), gap=16),
       "A centered sign in card: a user icon, the heading Welcome back, username and password "
       "fields, a Remember me checkbox with a Forgot password? link next to it, a full width Sign "
       "in button, a divider, a Continue with Google button and a Create an account link. Sign in "
       "must show an error when the fields are empty, and Create an account opens a Register page.",
       [click("Sign in", type="validate_required"),
        click("Create an account", type="navigate", page="Register")])

screen("login_04", "login", "Admin portal", DESKTOP,
       ROW(IMG(430, glyph="mountain", alt="illustration"),
           COL(H("Admin Portal"), TX("Please sign in to continue"), I("Email", "email"),
               I("Password", "password"), SEL("Role", options=["Admin", "Editor", "Viewer"]),
               B("Login", 200), L("Need help?"), gap=16), weights=[1, 1], gap=50),
       "An admin login screen split in two: an illustration on the left; on the right the heading "
       "Admin Portal, a line 'Please sign in to continue', email and password fields, a Role "
       "dropdown with Admin, Editor and Viewer, a Login button and a Need help? link. Login shows "
       "an error if fields are empty and checks that the email is valid.",
       [click("Login", type="validate_required"),
        click("Login", type="validate_format", field_label="Email", format="email")])

# ---------------------------------------------------------------- registration
screen("reg_01", "registration", "Create account", MOBILE,
       COL(H("Create Account", 1, "center"), I("Full name"), I("Email", "email"),
           I("Password", "password"), I("Confirm password", "password"),
           CB("I agree to the terms"), B("Register", "full"),
           L("Already have an account? Login", "center"), gap=18),
       "A registration page titled Create Account with full name, email, password and confirm "
       "password fields, an I agree to the terms checkbox, a Register button and a link 'Already "
       "have an account? Login'. Register shows an error if any field is empty and the link goes "
       "to the Login page.",
       [click("Register", type="validate_required"),
        click("Already have an account? Login", type="navigate", page="Login")])

screen("reg_02", "registration", "Sign up", NARROW,
       CARD(H("Sign up"), ROW(I("First name"), I("Last name")), I("Email", "email"),
            ROW(I("Phone", "tel"), SEL("Country", options=["India", "USA", "UK"])),
            I("Password", "password"), TX("Gender"),
            ROW(RB("Male"), RB("Female"), RB("Other"), weights=[1, 1, 1]),
            B("Create account"), gap=16),
       "A sign up form in a card: heading Sign up, first name and last name side by side, email, "
       "phone next to a Country dropdown (India, USA, UK), password, a Gender choice with Male, "
       "Female and Other radio buttons, and a Create account button that shows an error when "
       "required fields are empty.",
       [click("Create account", type="validate_required")])

screen("reg_03", "registration", "Join the club", DESKTOP,
       ROW(COL(H("Join the club"), P(2), I("Name"), I("Email", "email"), I("Password", "password"),
               CB("Subscribe to newsletter"),
               ROW(B("Sign up", 170), B("Cancel", 170, style="double"), weights=[1, 1]), gap=16),
           IMG(400, glyph="x", alt="people"), weights=[1.1, 1], gap=50),
       "A membership sign up page with the heading Join the club and a short intro paragraph, name, "
       "email and password fields, a Subscribe to newsletter checkbox, and Sign up and Cancel "
       "buttons; a large photo sits on the right. Sign up must validate that the fields are filled "
       "and then show the message Welcome aboard.",
       [click("Sign up", type="validate_required"),
        click("Sign up", type="show_message", text_contains="welcome")])

screen("reg_04", "registration", "Your details", MOBILE,
       COL(TX("Step 1 of 2"), H("Your details"), I("Username"), I("Email", "email"),
           I("Date of birth", "date"), SEL("City", options=["Hyderabad", "Delhi", "Mumbai"]),
           ROW(B("Back", "full", style="double"), B("Next", "full"), gap=20), gap=18),
       "Step one of a two step registration: a small 'Step 1 of 2' text, the heading Your details, "
       "username, email and date of birth fields, a City dropdown, and Back and Next buttons. Next "
       "goes to an Address page.",
       [click("Next", type="navigate", page="Address")])

# ---------------------------------------------------------------- dashboard
screen("dash_01", "dashboard", "Acme dashboard", DESKTOP,
       COL(NAV(left=[H("Acme", 2)], right=[NI("Home"), NI("Reports"), NI("Settings"), ICO("user")]),
           H("Dashboard"),
           ROW(CARD(H("1,240", 2), TX("Users")), CARD(H("$8,300", 2), TX("Revenue")),
               CARD(H("312", 2), TX("Orders"))),
           ROW(CARD(H("Sales", 3), IMG(200, glyph="chart", alt="sales chart")),
               CARD(H("Recent orders", 3), LST(["Order 1042", "Order 1041", "Order 1040", "Order 1039"])),
               weights=[2, 1]), gap=22),
       "An admin dashboard with a top navbar (Acme logo, Home, Reports and Settings links and a "
       "user icon), the heading Dashboard, three stat cards for Users, Revenue and Orders, a Sales "
       "chart card and a Recent orders list. Clicking Reports opens a Reports page.",
       [click("Reports", type="navigate", page="Reports")])

screen("dash_02", "dashboard", "Overview", DESKTOP,
       ROW(NAV(vertical=True, items=[H("Menu", 3), NI("Overview"), NI("Analytics"), NI("Customers"),
                                     NI("Logout")]),
           COL(HDR(H("Overview", 2), I("Search", "search", 260)),
               ROW(IMG(180, glyph="chart", alt="visits chart"), IMG(180, glyph="chart", alt="sales chart")),
               CARD(H("Tasks", 3), CB("Review reports"), CB("Call supplier"), CB("Update pricing"), gap=10),
               gap=20), weights=[1, 3.2], gap=30),
       "A dashboard with a left sidebar menu (Overview, Analytics, Customers, Logout), a header "
       "with the title Overview and a search box, two charts side by side and a Tasks card with "
       "three checkboxes: Review reports, Call supplier and Update pricing. Logout returns to a "
       "Login page.",
       [click("Logout", type="navigate", page="Login")])

screen("dash_03", "dashboard", "Wallet home", MOBILE,
       COL(HDR(ICO("menu"), H("Hi, Sam", 2)),
           CARD(TX("Balance"), H("$2,450")),
           ROW(B("Send", "full"), B("Request", "full", style="double")),
           H("Activity", 3), LST(["Coffee  -$4", "Salary  +$1,200", "Groceries  -$36"]), gap=20),
       "A mobile wallet home screen: a header with a menu icon and the greeting Hi, Sam, a balance "
       "card, Send and Request buttons, and an Activity heading with a list of recent "
       "transactions. Send opens a Send money page.",
       [click("Send", type="navigate", page="Send money")])

screen("dash_04", "dashboard", "Insight analytics", DESKTOP,
       COL(NAV(left=[H("Insight", 2)], right=[NI("Dashboard"), NI("Projects"), NI("Team"),
                                              B("New project")]),
           ROW(SEL("Last 30 days", 240, options=["Last 7 days", "Last 30 days", "This year"]),
               B("Export", 150, style="double"), weights=[1, 1]),
           IMG(240, glyph="chart", alt="traffic chart"),
           ROW(CARD(H("Tasks done", 3), P(2)), CARD(H("Open issues", 3), P(2))), gap=22),
       "An analytics dashboard with a navbar (Insight logo, Dashboard, Projects, Team and a New "
       "project button), a date range dropdown (Last 7 days, Last 30 days, This year) with an "
       "Export button, a large traffic chart and two cards, Tasks done and Open issues. Export "
       "shows the message Export started and New project opens a New project page.",
       [click("Export", type="show_message", text_contains="export"),
        click("New project", type="navigate", page="New project")])

# ---------------------------------------------------------------- profile
screen("prof_01", "profile", "Jane Doe", MOBILE,
       COL(IMG(140, 140, "center", shape="circle", alt="avatar"), H("Jane Doe", 1, "center"),
           TX("Product designer", "center"),
           ROW(B("Follow", "full"), B("Message", "full", style="double")), DIV(),
           H("About", 3), P(3), gap=18),
       "A profile page with a round avatar, the name Jane Doe, the role Product designer, Follow "
       "and Message buttons, a divider and an About section with a short bio. Follow shows the "
       "message Following and Message opens a Chat page.",
       [click("Follow", type="show_message", text_contains="following"),
        click("Message", type="navigate", page="Chat")])

screen("prof_02", "profile", "Edit profile", DESKTOP,
       COL(NAV(left=[H("Pulse", 2)], right=[NI("Home"), NI("Profile")]), H("Edit profile"),
           ROW(IMG(130, 130, shape="circle", alt="avatar"),
               COL(I("Full name"), I("Email", "email"), I("Phone", "tel"), gap=14),
               weights=[1, 4], gap=40),
           TA("Bio", 3), ROW(B("Save", 150), B("Cancel", 150, style="double"), weights=[1, 6]), gap=20),
       "An edit profile page: a navbar with the Pulse logo, Home and Profile links, the heading "
       "Edit profile, an avatar next to full name, email and phone fields, a Bio text area, and Save "
       "and Cancel buttons. Save checks the required fields and then shows Profile saved.",
       [click("Save", type="validate_required"),
        click("Save", type="show_message", text_contains="saved")])

screen("prof_03", "profile", "Alex Kim", DESKTOP,
       COL(IMG(150, "full", glyph="mountain", alt="cover"),
           ROW(IMG(110, 110, shape="circle", alt="avatar"),
               COL(H("Alex Kim", 2), TX("@alexk"), gap=6),
               B("Edit profile", 190, "right"), weights=[1, 3, 2], gap=24, valign="center"),
           ROW(TX("120 posts"), TX("4.5k followers"), TX("300 following")),
           H("Posts", 3),
           ROW(IMG(150, alt="post"), IMG(150, alt="post"), IMG(150, alt="post")), gap=20),
       "A social profile with a cover image, a round avatar, the name Alex Kim with the handle "
       "@alexk, an Edit profile button, counts for posts, followers and following, and a Posts "
       "section with a grid of three photos. Edit profile opens an Edit profile page.",
       [click("Edit profile", type="navigate", page="Edit profile")])

screen("prof_04", "profile", "My account", MOBILE,
       COL(H("My Account"),
           CARD(ROW(IMG(70, 70, shape="circle", alt="avatar"),
                    COL(TX("Priya Shah"), TX("priya@mail.com"), gap=4), weights=[1, 3], gap=16,
                    valign="center")),
           L("My orders"), L("Saved addresses"), L("Payment methods"), DIV(),
           B("Log out", "full", style="double"), gap=20),
       "An account screen titled My Account with a card showing the user's avatar, name and "
       "email, links to My orders, Saved addresses and Payment methods, a divider and a Log out "
       "button. Log out returns to the Login page and My orders opens an Orders page.",
       [click("Log out", type="navigate", page="Login"),
        click("My orders", type="navigate", page="Orders")])

# ---------------------------------------------------------------- ecommerce
screen("shop_01", "ecommerce", "ShopEasy", DESKTOP,
       COL(NAV(left=[H("ShopEasy", 2)], right=[I("Search products", "search", 280), NI("Cart")]),
           H("New arrivals"),
           ROW(CARD(IMG(150, alt="product"), TX("Canvas bag"), TX("$29"), B("Add to cart", "full")),
               CARD(IMG(150, alt="product"), TX("Desk lamp"), TX("$45"), B("Buy lamp", "full")),
               CARD(IMG(150, alt="product"), TX("Sneakers"), TX("$80"), B("Buy sneakers", "full"))),
           gap=22),
       "A shop home page with a navbar (ShopEasy logo, a search box and a Cart link), the heading "
       "New arrivals and three product cards (Canvas bag $29, Desk lamp $45, Sneakers $80), each "
       "with a photo and a button. Add to cart shows the message Added to cart and Cart opens a "
       "Cart page.",
       [click("Add to cart", type="show_message", text_contains="added"),
        click("Cart", type="navigate", page="Cart")])

screen("shop_02", "ecommerce", "Running shoes", DESKTOP,
       ROW(IMG(400, glyph="x", alt="shoe"),
           COL(H("Running Shoes"), H("$89", 2), P(3),
               SEL("Size", options=["7", "8", "9", "10"]), I("Quantity", "number", 160),
               ROW(B("Add to cart", "full"), B("Buy now", "full", style="double"), gap=18), gap=16),
           weights=[1, 1], gap=50),
       "A product detail page: a big product photo on the left; on the right the title Running "
       "Shoes, the price $89, a description, a Size dropdown (7 to 10), a Quantity field and Add to "
       "cart and Buy now buttons. Add to cart shows Added to cart and Buy now goes to a Checkout "
       "page.",
       [click("Add to cart", type="show_message", text_contains="added"),
        click("Buy now", type="navigate", page="Checkout")])

screen("shop_03", "ecommerce", "Your cart", MOBILE,
       COL(H("Your cart"),
           CARD(ROW(IMG(80, 80, alt="item"), COL(TX("Linen shirt"), TX("$40"), gap=6),
                    weights=[1, 3], gap=16)),
           CARD(ROW(IMG(80, 80, alt="item"), COL(TX("Straw hat"), TX("$80"), gap=6),
                    weights=[1, 3], gap=16)),
           DIV(), ROW(TX("Total"), TX("$120", "right")), I("Coupon code"),
           B("Checkout", "full"), gap=18),
       "A shopping cart screen titled Your cart with two item cards (Linen shirt $40 and Straw hat "
       "$80, each with a thumbnail), the total $120, a coupon code field and a Checkout button "
       "that opens a Checkout page.",
       [click("Checkout", type="navigate", page="Checkout")])

screen("shop_04", "ecommerce", "Checkout", DESKTOP,
       COL(H("Checkout"),
           ROW(COL(H("Shipping", 3), I("Full name"), I("Address"), ROW(I("City"), I("Zip code")),
                   H("Payment", 3), RB("Card"), RB("PayPal"), RB("Cash on delivery"), gap=14),
               CARD(H("Order summary", 3), LST(["Linen shirt  $40", "Straw hat  $14"]), DIV(),
                    TX("Total $54"), B("Place order", "full")),
               weights=[1.5, 1], gap=40), gap=20),
       "A checkout page: a Shipping section with full name, address, city and zip code fields, a "
       "Payment section with Card, PayPal and Cash on delivery options, and an Order summary card "
       "with the items, the total and a Place order button. Place order shows an error when the "
       "shipping fields are empty.",
       [click("Place order", type="validate_required")])

# ---------------------------------------------------------------- banking
screen("bank_01", "banking", "MyBank", MOBILE,
       COL(HDR(H("MyBank", 2), ICO("bell", "right")),
           CARD(TX("Savings account"), H("$12,480.50")),
           ROW(B("Transfer", "full"), B("Pay bills", "full"), B("Deposit", "full"), gap=14),
           H("Transactions", 3), LST(["Rent  -$900", "Salary  +$3,100", "Netflix  -$12"]), gap=20),
       "A banking app home: a header with the MyBank title and a bell icon, a savings account "
       "balance card, Transfer, Pay bills and Deposit buttons, and a Transactions list. Transfer "
       "opens a Transfer page.",
       [click("Transfer", type="navigate", page="Transfer")])

screen("bank_02", "banking", "Transfer money", DESKTOP,
       COL(NAV(left=[H("NorthBank", 2)], right=[NI("Accounts"), NI("Transfers"), NI("Cards"), NI("Logout")]),
           H("Transfer money"),
           CARD(SEL("From account", options=["Savings", "Current"]),
                I("Recipient account number", "number"), I("Amount", "number"), I("Reference"),
                CB("Save recipient"),
                ROW(B("Send", 150), B("Cancel", 150, style="double"), weights=[1, 4]), gap=16),
           gap=22),
       "A money transfer page with a navbar (NorthBank logo, Accounts, Transfers, Cards, Logout), "
       "the heading Transfer money and a card with a From account dropdown (Savings, Current), "
       "recipient account number, amount and reference fields, a Save recipient checkbox and Send "
       "and Cancel buttons. Send must show an error if the required fields are empty.",
       [click("Send", type="validate_required")])

screen("bank_03", "banking", "Cards", DESKTOP,
       COL(NAV(left=[H("NorthBank", 2)], right=[NI("Accounts"), NI("Cards"), NI("Help")]),
           H("My cards"),
           ROW(CARD(H("Visa 4821", 3), TX("Balance $3,200"), B("Freeze card", 200, style="double")),
               CARD(H("Mastercard 7710", 3), TX("Balance $940"), B("View statement", 200))),
           H("Spending", 3), IMG(200, glyph="chart", alt="spending chart"), gap=20),
       "A cards overview with a navbar, the heading My cards, two card panels (Visa 4821 with a "
       "Freeze card button and Mastercard 7710 with a View statement button) and a Spending chart. "
       "Freeze card shows the message Card frozen and View statement opens a Statement page.",
       [click("Freeze card", type="show_message", text_contains="frozen"),
        click("View statement", type="navigate", page="Statement")])

screen("bank_04", "banking", "Loan calculator", MOBILE,
       COL(H("Loan calculator"), I("Loan amount", "number"), I("Interest rate", "number"),
           SEL("Term", options=["12 months", "24 months", "36 months"]),
           B("Calculate", "full"),
           CARD(TX("Monthly payment"), H("$0", 2)), gap=18),
       "A loan calculator with loan amount and interest rate fields, a Term dropdown (12, 24 or 36 "
       "months), a Calculate button and a result card showing the monthly payment. Calculate shows "
       "an error if the amount or rate is empty.",
       [click("Calculate", type="validate_required")])

# ---------------------------------------------------------------- booking
screen("book_01", "booking", "StayFinder", DESKTOP,
       COL(NAV(left=[H("StayFinder", 2)], right=[NI("Hotels"), NI("Flights"), NI("Deals"), B("Sign in")]),
           IMG(200, "full", glyph="mountain", alt="beach banner"),
           CARD(ROW(I("Destination"), I("Check-in", "date"), I("Check-out", "date"),
                    SEL("Guests", options=["1", "2", "3", "4"]), B("Search", "full"),
                    weights=[1.6, 1, 1, 0.8, 0.8], gap=14)), gap=22),
       "A hotel booking home page: a navbar with StayFinder, Hotels, Flights, Deals and a Sign in "
       "button, a wide banner photo and a search card with destination, check-in and check-out date "
       "fields, a Guests dropdown and a Search button. Search shows an error when the fields are "
       "empty.",
       [click("Search", type="validate_required")])

screen("book_02", "booking", "Book appointment", MOBILE,
       COL(H("Book appointment"), SEL("Select doctor", options=["Dr. Rao", "Dr. Mehta", "Dr. Lee"]),
           I("Date", "date"), TX("Time slot"),
           ROW(RB("9:00"), RB("11:00"), RB("15:00")), TA("Reason for visit", 3),
           B("Confirm booking", "full"), gap=18),
       "A doctor appointment form titled Book appointment with a Select doctor dropdown, a date "
       "field, time slot radio buttons for 9:00, 11:00 and 15:00, a reason for visit text area and a "
       "Confirm booking button that shows an error if the date is missing and otherwise shows "
       "Appointment booked.",
       [click("Confirm booking", type="validate_required"),
        click("Confirm booking", type="show_message", text_contains="booked")])

screen("book_03", "booking", "Flights to Paris", DESKTOP,
       COL(H("Flights to Paris"),
           ROW(SEL("Sort by", 240, options=["Price", "Duration"]), CB("Non-stop only"), weights=[1, 2]),
           CARD(ROW(TX("Air France"), TX("08:10 - 10:25"), H("$210", 3), B("Select flight", 180),
                    weights=[1, 1, 0.7, 1], valign="center"), dir="col"),
           CARD(ROW(TX("Lufthansa"), TX("13:40 - 16:05"), H("$185", 3), B("Choose", 180),
                    weights=[1, 1, 0.7, 1], valign="center"), dir="col"),
           B("Load more", 200, "center", style="double"), gap=20),
       "A flight results page titled Flights to Paris with a Sort by dropdown, a Non-stop only "
       "checkbox, two flight result cards (Air France with a Select flight button and Lufthansa "
       "with a Choose button) and a Load more button. Select flight opens a Passenger details page.",
       [click("Select flight", type="navigate", page="Passenger details")])

screen("book_04", "booking", "Jazz Night", DESKTOP,
       COL(NAV(left=[H("Eventix", 2)], right=[NI("Events"), NI("Venues"), NI("My tickets")]),
           ROW(IMG(320, glyph="x", alt="poster"),
               COL(H("Jazz Night"), TX("Sat 12 Dec, 8 PM"), P(2),
                   SEL("Tickets", 220, options=["1", "2", "3", "4"]), B("Book now", 200),
                   L("View venue map"), gap=16), weights=[1, 1.4], gap=44), gap=24),
       "An event page with a navbar (Eventix, Events, Venues, My tickets), a poster image, the "
       "title Jazz Night, the date Sat 12 Dec 8 PM, a short description, a Tickets dropdown, a Book "
       "now button and a View venue map link. Book now goes to a Checkout page and View venue map "
       "opens a Venue page.",
       [click("Book now", type="navigate", page="Checkout"),
        click("View venue map", type="navigate", page="Venue")])

# ---------------------------------------------------------------- contact
screen("contact_01", "contact", "Contact us", MOBILE,
       COL(H("Contact us"), P(2), I("Name"), I("Email", "email"), TA("Message", 4),
           B("Send", "full"), gap=18),
       "A contact page with the heading Contact us, a short intro text, name and email fields, a "
       "message box and a Send button. Send shows an error when fields are empty and checks the "
       "email format.",
       [click("Send", type="validate_required"),
        click("Send", type="validate_format", field_label="Email", format="email")])

screen("contact_02", "contact", "Get in touch", DESKTOP,
       COL(NAV(left=[H("Acme", 2)], right=[NI("Home"), NI("Services"), NI("Contact")]),
           H("Get in touch"),
           ROW(COL(I("Name"), I("Email", "email"), I("Subject"), TA("Message", 4), B("Submit", 170),
                   gap=14),
               COL(IMG(210, glyph="mountain", alt="map"), TX("123 Main St, Springfield"),
                   TX("+1 555 0100"), TX("hello@acme.com"), gap=10), weights=[1.3, 1], gap=44),
           gap=22),
       "A contact page with a navbar (Acme, Home, Services, Contact), the heading Get in touch, a "
       "form with name, email, subject and message and a Submit button, and on the right a map "
       "image with the address, phone number and email. Submit shows an error if fields are empty.",
       [click("Submit", type="validate_required")])

screen("contact_03", "contact", "Support request", NARROW,
       FORM(H("Support request"), ROW(I("First name"), I("Last name")),
            SEL("Topic", options=["Billing", "Technical", "Other"]), TX("Priority"),
            ROW(RB("Low"), RB("Medium"), RB("High")), TA("Describe the issue", 4),
            CB("Email me a copy"), B("Submit ticket", 210), gap=16),
       "A support request form with first and last name side by side, a Topic dropdown (Billing, "
       "Technical, Other), Low, Medium and High priority radio buttons, a text area to describe the "
       "issue, an Email me a copy checkbox and a Submit ticket button that shows an error when "
       "required fields are empty.",
       [click("Submit ticket", type="validate_required")])

screen("contact_04", "contact", "Acme Studio", DESKTOP,
       COL(HDR(H("Acme Studio", 2)),
           ROW(CARD(ICO("phone"), H("Call", 3), TX("+1 555 0199")),
               CARD(ICO("mail"), H("Email", 3), TX("hi@acme.studio")),
               CARD(ICO("pin"), H("Visit", 3), TX("12 Park Lane"))),
           H("Newsletter", 3),
           ROW(I("Your email", "email"), B("Subscribe", "full"), weights=[3, 1]), gap=22),
       "A studio contact page with a header (Acme Studio), three cards for Call, Email and Visit "
       "each with an icon and details, and a Newsletter section with an email field and a Subscribe "
       "button that checks the email is valid.",
       [click("Subscribe", type="validate_format", field_label="Your email", format="email")])

# ---------------------------------------------------------------- settings
screen("set_01", "settings", "Settings", MOBILE,
       COL(H("Settings"), TX("Notifications"), CB("Push notifications", toggle=True),
           CB("Email updates", toggle=True), CB("Dark mode", toggle=True), DIV(),
           L("Privacy policy"), B("Log out", "full", style="double"), gap=20),
       "A mobile settings screen with the heading Settings, a Notifications section with toggles "
       "for push notifications, email updates and dark mode, a divider, a Privacy policy link and a "
       "Log out button that returns to the Login page.",
       [click("Log out", type="navigate", page="Login")])

screen("set_02", "settings", "General settings", DESKTOP,
       ROW(NAV(vertical=True, items=[NI("General"), NI("Security"), NI("Billing"), NI("Notifications")]),
           COL(H("General"), I("Display name"), I("Email", "email"),
               SEL("Language", options=["English", "Hindi", "Telugu"]),
               SEL("Time zone", options=["IST", "UTC", "PST"]), B("Save changes", 200), gap=16),
           weights=[1, 3], gap=40),
       "A settings page with a sidebar (General, Security, Billing, Notifications) and a General "
       "section with display name and email fields, Language (English, Hindi, Telugu) and Time zone "
       "dropdowns and a Save changes button. Save changes shows Settings saved and Security opens a "
       "Security page.",
       [click("Save changes", type="show_message", text_contains="saved"),
        click("Security", type="navigate", page="Security")])

screen("set_03", "settings", "Security", NARROW,
       COL(H("Security"),
           CARD(H("Change password", 3), I("Current password", "password"),
                I("New password", "password"), I("Confirm new password", "password"),
                B("Update password", 220)),
           CARD(H("Two-factor authentication", 3), P(1), CB("Enable 2FA")), gap=20),
       "A security settings page with a Change password card (current password, new password and "
       "confirm new password fields and an Update password button) and a Two-factor authentication "
       "card with an Enable 2FA checkbox. Update password shows an error when fields are empty.",
       [click("Update password", type="validate_required")])

screen("set_04", "settings", "Privacy", MOBILE,
       COL(HDR(ICO("back"), H("Privacy", 2)), TX("Profile visibility"), RB("Public"),
           RB("Friends only"), RB("Private"), DIV(), CB("Show online status"), CB("Allow tagging"),
           ROW(B("Reset", "full", style="double"), B("Save", "full")), gap=18),
       "A privacy settings screen with a back icon and the title Privacy, profile visibility "
       "options Public, Friends only and Private, a divider, Show online status and Allow tagging "
       "checkboxes, and Reset and Save buttons. Save shows the message Privacy settings saved.",
       [click("Save", type="show_message", text_contains="saved")])

# ---------------------------------------------------------------- landing
screen("land_01", "landing", "Nimbus", DESKTOP,
       COL(NAV(left=[H("Nimbus", 2)], right=[NI("Features"), NI("Pricing"), NI("About"), B("Get started")]),
           ROW(COL(H("Cloud storage made simple"), P(3),
                   ROW(B("Try free", "full"), B("Learn more", "full", style="double"), gap=18), gap=18),
               IMG(300, glyph="x", alt="hero"), weights=[1, 1], gap=44),
           ROW(CARD(ICO("bolt"), H("Fast", 3), P(2)), CARD(ICO("lock"), H("Secure", 3), P(2)),
               CARD(ICO("cloud"), H("Synced", 3), P(2))), gap=28),
       "A landing page for Nimbus: a navbar with Features, Pricing, About and a Get started button, "
       "a hero with the headline Cloud storage made simple, a paragraph, Try free and Learn more "
       "buttons and a hero image, and three feature cards: Fast, Secure and Synced. Try free opens "
       "a Sign up page and Pricing opens a Pricing page.",
       [click("Try free", type="navigate", page="Sign up"),
        click("Pricing", type="navigate", page="Pricing")])

screen("land_02", "landing", "Buildr", DESKTOP,
       COL(NAV(left=[H("Buildr", 2)], right=[NI("Product"), NI("Docs"), NI("Blog")]),
           H("Build apps faster", 1, "center"), P(2, 0.6, "center"),
           ROW(SP(1), I("Work email", "email"), B("Join waitlist", "full"), SP(1), weights=[0.5, 2, 1, 0.5]),
           IMG(220, "full", glyph="mountain", alt="product screenshot"),
           H("Loved by teams", 3, "center"),
           ROW(IMG(70, alt="logo"), IMG(70, alt="logo"), IMG(70, alt="logo"), IMG(70, alt="logo")),
           gap=22),
       "A product landing page for Buildr with a navbar (Product, Docs, Blog), a centered headline "
       "Build apps faster with a subtitle, a work email field with a Join waitlist button, a "
       "product screenshot and a Loved by teams row of four customer logos. Join waitlist checks "
       "that the email is valid and then shows You are on the list.",
       [click("Join waitlist", type="validate_format", field_label="Work email", format="email"),
        click("Join waitlist", type="show_message", text_contains="list")])

screen("land_03", "landing", "FitTrack", MOBILE,
       COL(IMG(220, "full", glyph="x", alt="app hero"), H("FitTrack", 1, "center"), P(2, 1, "center"),
           B("Download app", "full"), B("Watch demo", "full", style="double"),
           ROW(ICO("heart", "center"), ICO("bolt", "center"), ICO("star", "center")), gap=20),
       "A mobile landing page for the FitTrack app: a hero image, the app name FitTrack, a short "
       "tagline, Download app and Watch demo buttons and a row of three feature icons. Download "
       "app shows the message Coming soon and Watch demo opens a Demo page.",
       [click("Download app", type="show_message", text_contains="coming soon"),
        click("Watch demo", type="navigate", page="Demo")])

screen("land_04", "landing", "Pricing", DESKTOP,
       COL(NAV(left=[H("Flowly", 2)], right=[NI("Features"), NI("Pricing"), NI("Login")]),
           H("Simple pricing", 1, "center"),
           ROW(CARD(H("Basic", 3), H("$9", 2), LST(["1 user", "5 projects"]), B("Choose Basic", "full")),
               CARD(H("Pro", 3), H("$29", 2), LST(["5 users", "Unlimited projects"]), B("Choose Pro", "full")),
               CARD(H("Team", 3), H("$99", 2), LST(["50 users", "Priority support"]),
                    B("Contact sales", "full", style="double")), gap=26), gap=24),
       "A pricing page for Flowly with a navbar (Features, Pricing, Login), the heading Simple "
       "pricing and three plan cards: Basic $9, Pro $29 and Team $99, each with a feature list and "
       "a button (Choose Basic, Choose Pro, Contact sales). Choose Pro shows the message Pro plan "
       "selected and Contact sales opens a Contact page.",
       [click("Choose Pro", type="show_message", text_contains="pro"),
        click("Contact sales", type="navigate", page="Contact")])

assert len(SCREENS) == 40, len(SCREENS)
assert len({s["id"] for s in SCREENS}) == 40
