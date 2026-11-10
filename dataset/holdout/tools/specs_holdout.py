"""Held-out screen specifications (20 screens, 2 per category). NEVER used to tune the pipeline.

Layouts differ from the 40 development screens in dataset/tools/specs.py (OTP phone login, SSO split screen,
team invite rows, student sign-up with avatar upload, fleet dashboard with 4 stat cards, fitness rings,
company profile with tabs, doctor profile, wishlist grid, order tracking, bill payment, portfolio,
restaurant reservation, car rental with filter panel, feedback survey, office locations, notification matrix,
connected apps, restaurant landing, conference landing).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from specs import (B, BOX, CARD, CB, COL, DIV, FORM, H, HDR, I, ICO, IMG, L, LST, NAV, NI, P, RB,  # noqa: E402,F401
                   ROW, SEL, SP, TA, TX, DESKTOP, MOBILE, NARROW, click)

SCREENS = []


def screen(id, category, title, mode, root, instruction, interactions=()):
    SCREENS.append(dict(id=id, category=category, title=title, mode=mode, root=root,
                        instruction=instruction, interactions=list(interactions)))


# ---------------------------------------------------------------- login
screen("hold_login_01", "login", "Phone login", MOBILE,
       COL(ICO("back"), H("Enter your phone", 1), TX("We will text you a code"),
           I("Phone number", "tel"), B("Send code", "full"), SP(6), L("Use email instead", "center"), gap=20),
       "A phone number login screen with a back icon, the heading Enter your phone, the text We will text you a "
       "code, a Phone number field, a full width Send code button and a Use email instead link. Send code shows "
       "an error when the phone number is empty and Use email instead opens an Email login page.",
       [click("Send code", type="validate_required"),
        click("Use email instead", type="navigate", page="Email login")])

screen("hold_login_02", "login", "Workspace sign in", DESKTOP,
       ROW(COL(IMG(300, "full", glyph="mountain", alt="team photo"), H("Work together", 2), P(3)),
           CARD(H("Sign in to your workspace", 2), I("Work email", "email"), B("Continue", "full"), DIV(),
                B("Continue with GitHub", "full", style="double"), B("Continue with Microsoft", "full", style="double"),
                L("Create a workspace", "center"), gap=16),
           weights=[1, 1], gap=40),
       "A split screen: on the left a team photo, the heading Work together and a short paragraph; on the right a "
       "card with the heading Sign in to your workspace, a Work email field, a full width Continue button, a "
       "divider, Continue with GitHub and Continue with Microsoft buttons and a Create a workspace link. Continue "
       "checks that the email is valid and Create a workspace opens a Workspace setup page.",
       [click("Continue", type="validate_format", field_label="Work email", format="email"),
        click("Create a workspace", type="navigate", page="Workspace setup")])

# ---------------------------------------------------------------- registration
screen("hold_reg_01", "registration", "Invite your team", NARROW,
       COL(H("Invite your team", 1), TX("Add the people you work with"),
           ROW(I("Teammate email 1", "email"), SEL("Role", None, ["Admin", "Member"]), weights=[2, 1]),
           ROW(I("Teammate email 2", "email"), SEL("Role", None, ["Admin", "Member"]), weights=[2, 1]),
           ROW(I("Teammate email 3", "email"), SEL("Role", None, ["Admin", "Member"]), weights=[2, 1]),
           L("Add another"), SP(6),
           ROW(B("Send invites"), B("Skip for now", style="double"), weights=[1, 1], gap=20), gap=18),
       "A team invitation step with the heading Invite your team, the text Add the people you work with, three "
       "rows each with a teammate email field and a Role dropdown (Admin, Member), an Add another link, and Send "
       "invites and Skip for now buttons. Send invites checks that the emails are valid and Skip for now opens a "
       "Dashboard page.",
       [click("Send invites", type="validate_format", field_label="Teammate email 1", format="email"),
        click("Skip for now", type="navigate", page="Dashboard")])

screen("hold_reg_02", "registration", "Student sign up", MOBILE,
       COL(H("Student sign up", 1, "center"), IMG(120, 120, "center", shape="circle", alt="profile photo"),
           L("Upload a photo", "center"), I("Full name"), I("School name"),
           SEL("Year of study", None, ["1st", "2nd", "3rd", "4th"]),
           CB("I am over 13"), CB("Send me study tips"), B("Join now", "full"), gap=16),
       "A student sign up page with the heading Student sign up, a round profile photo with an Upload a photo "
       "link, Full name and School name fields, a Year of study dropdown (1st, 2nd, 3rd, 4th), I am over 13 and "
       "Send me study tips checkboxes and a full width Join now button. Join now shows an error if the fields are "
       "empty.",
       [click("Join now", type="validate_required")])

# ---------------------------------------------------------------- dashboard
screen("hold_dash_01", "dashboard", "Fleet tracker", DESKTOP,
       COL(HDR(H("Fleet tracker", 2), I("Search vehicles", "search", 260), B("Add vehicle", align="right"), gap=24),
           ROW(CARD(H("Active", 3), TX("42")), CARD(H("Idle", 3), TX("7")), CARD(H("In service", 3), TX("3")),
               CARD(H("Alerts", 3), TX("5")), gap=16),
           ROW(IMG(300, "full", glyph="mountain", alt="live map"),
               CARD(H("Vehicles", 3), LST(["Truck 12", "Van 04", "Truck 31", "Bike 09"])),
               weights=[2, 1], gap=24), gap=22),
       "A fleet tracking dashboard: a header with the title Fleet tracker, a Search vehicles box and an Add "
       "vehicle button; four stat cards Active, Idle, In service and Alerts; below, a large live map image and a "
       "Vehicles card listing Truck 12, Van 04, Truck 31 and Bike 09. Add vehicle opens an Add vehicle page.",
       [click("Add vehicle", type="navigate", page="Add vehicle")])

screen("hold_dash_02", "dashboard", "Today", MOBILE,
       COL(HDR(ICO("menu"), H("Today", 2), ICO("bell", "right"), gap=20),
           IMG(200, 200, "center", shape="circle", alt="progress ring"),
           ROW(CARD(H("Steps", 3), TX("8400")), CARD(H("Calories", 3), TX("520")), CARD(H("Sleep", 3), TX("7h")),
               gap=12),
           B("Start workout", "full"), L("View history", "center"), gap=20),
       "A fitness dashboard on a phone: a header with a menu icon, the title Today and a bell icon, a big round "
       "progress ring, three small cards Steps, Calories and Sleep, a full width Start workout button and a View "
       "history link. Start workout shows the message Workout started and View history opens a History page.",
       [click("Start workout", type="show_message", text_contains="workout started"),
        click("View history", type="navigate", page="History")])

# ---------------------------------------------------------------- profile
screen("hold_prof_01", "profile", "Company profile", DESKTOP,
       COL(IMG(170, "full", glyph="mountain", alt="cover photo"),
           ROW(IMG(110, 110, shape="circle", alt="company logo"),
               COL(H("Orbit Labs", 1), TX("Space software company")),
               B("Follow Company", 200, "right"), weights=[1, 3, 2], valign="center"),
           NAV(left=[NI("About"), NI("Jobs"), NI("People")]),
           P(3, 0.9),
           H("Open roles", 2), LST(["Backend engineer", "Product designer", "Data analyst"]), gap=20),
       "A company profile page with a wide cover photo, a round company logo, the name Orbit Labs with the line "
       "Space software company and a Follow Company button, a tab bar with About, Jobs and People, a short "
       "paragraph and an Open roles section listing Backend engineer, Product designer and Data analyst. Follow "
       "Company shows the message Following Orbit Labs and Jobs opens a Jobs page.",
       [click("Follow Company", type="show_message", text_contains="following"),
        click("Jobs", type="navigate", page="Jobs")])

screen("hold_prof_02", "profile", "Dr. Rao", MOBILE,
       COL(IMG(160, 160, "center", shape="circle", alt="doctor photo"), H("Dr. Meera Rao", 1, "center"),
           TX("Cardiologist", "center"),
           ROW(B("Book visit"), B("Call clinic", style="double"), weights=[1, 1], gap=16),
           H("Patient reviews", 2), TA("Write a review", 3), B("Post review", "full"), gap=18),
       "A doctor profile on a phone: a round photo, the name Dr. Meera Rao, the speciality Cardiologist, Book "
       "visit and Call clinic buttons, a Patient reviews heading, a Write a review text area and a full width "
       "Post review button. Book visit opens a Booking page and Post review shows an error if the review is empty.",
       [click("Book visit", type="navigate", page="Booking"),
        click("Post review", type="validate_required")])

# ---------------------------------------------------------------- ecommerce
screen("hold_shop_01", "ecommerce", "Wishlist", DESKTOP,
       COL(HDR(H("My wishlist", 2), SEL("Sort by", 220, ["Newest", "Price"]), gap=24),
           ROW(CARD(IMG(120, "full", glyph="x", alt="mug"), TX("Ceramic mug"), TX("$12"), B("Move to cart", "full")),
               CARD(IMG(120, "full", glyph="x", alt="notebook"), TX("Notebook"), TX("$8"), B("Move to cart", "full")),
               CARD(IMG(120, "full", glyph="x", alt="backpack"), TX("Backpack"), TX("$55"), B("Move to cart", "full")),
               CARD(IMG(120, "full", glyph="x", alt="bottle"), TX("Water bottle"), TX("$18"), B("Move to cart", "full")),
               gap=14), gap=24),
       "A wishlist page with the title My wishlist and a Sort by dropdown (Newest, Price), then four product "
       "cards in a row: Ceramic mug $12, Notebook $8, Backpack $55 and Water bottle $18, each with a photo and a "
       "Move to cart button. Move to cart shows the message Moved to cart.",
       [click("Move to cart", type="show_message", text_contains="moved to cart")])

screen("hold_shop_02", "ecommerce", "Track order", MOBILE,
       COL(H("Track your order", 1), I("Order number"), B("Track", "full"),
           CARD(H("Delivery status", 3), LST(["Packed", "Shipped", "Out for delivery"])),
           L("Need help with this order?", "center"), gap=20),
       "An order tracking page with the heading Track your order, an Order number field, a full width Track "
       "button, a Delivery status card listing Packed, Shipped and Out for delivery, and a Need help with this "
       "order? link. Track shows an error when the order number is empty and the link opens a Support page.",
       [click("Track", type="validate_required"),
        click("Need help with this order?", type="navigate", page="Support")])

# ---------------------------------------------------------------- banking
screen("hold_bank_01", "banking", "Pay a bill", NARROW,
       COL(H("Pay a bill", 1), SEL("Biller", None, ["Electricity", "Water", "Internet"]),
           I("Account number"), I("Amount", "number"), I("Pay on", "date"),
           CB("Repeat monthly"), ROW(B("Pay now"), B("Cancel", style="double"), weights=[1, 1], gap=20), gap=16),
       "A bill payment form with the heading Pay a bill, a Biller dropdown (Electricity, Water, Internet), "
       "Account number, Amount and Pay on date fields, a Repeat monthly checkbox, and Pay now and Cancel buttons. "
       "Pay now shows an error if required fields are empty and Cancel opens an Accounts page.",
       [click("Pay now", type="validate_required"),
        click("Cancel", type="navigate", page="Accounts")])

screen("hold_bank_02", "banking", "Portfolio", DESKTOP,
       COL(NAV(left=[NI("Wealthly"), NI("Portfolio"), NI("Markets")], right=[NI("Support"), ICO("user")]),
           H("Your portfolio", 1), IMG(220, "full", glyph="chart", alt="portfolio chart"),
           ROW(CARD(H("Index fund", 3), TX("$4,200"), ROW(B("Buy"), B("Sell", style="double"), weights=[1, 1], gap=12)),
               CARD(H("Gold ETF", 3), TX("$1,150"), ROW(B("Buy more"), B("Sell all", style="double"), weights=[1, 1], gap=12)),
               CARD(H("Tech stocks", 3), TX("$2,980"), ROW(B("Add funds"), B("Withdraw", style="double"), weights=[1, 1], gap=12)),
               gap=16), gap=20),
       "An investment portfolio page with a navbar (Wealthly logo, Portfolio, Markets, Support and a user icon), "
       "the heading Your portfolio, a large portfolio chart and three holding cards: Index fund $4,200 with Buy "
       "and Sell buttons, Gold ETF $1,150 with Buy more and Sell all buttons and Tech stocks $2,980 with Add "
       "funds and Withdraw buttons. Sell all shows the message Order placed and Markets opens a Markets page.",
       [click("Sell all", type="show_message", text_contains="order placed"),
        click("Markets", type="navigate", page="Markets")])

# ---------------------------------------------------------------- booking
screen("hold_book_01", "booking", "Reserve a table", MOBILE,
       COL(H("Reserve a table", 1), SEL("Party size", None, ["1", "2", "4", "6"]), I("Date", "date"),
           RB("7:00 pm"), RB("8:30 pm"), I("Your name"), I("Phone", "tel"), TA("Special requests", 2),
           B("Reserve", "full"), gap=14),
       "A restaurant reservation page with the heading Reserve a table, a Party size dropdown (1, 2, 4, 6), a Date "
       "field, 7:00 pm and 8:30 pm radio buttons, Your name and Phone fields, a Special requests text area and a "
       "full width Reserve button. Reserve shows an error if the date or name is empty, otherwise the message "
       "Table reserved.",
       [click("Reserve", type="validate_required")])

screen("hold_book_02", "booking", "Rent a car", DESKTOP,
       COL(NAV(left=[NI("DriveNow"), NI("Cars"), NI("Locations")], right=[B("My trips")]),
           ROW(CARD(H("Filters", 3), CB("SUV"), CB("Sedan"), CB("Electric"), I("Pickup city"), B("Apply", "full")),
               COL(CARD(ROW(IMG(110, "full", glyph="x", alt="suv"), COL(H("Urban SUV", 3), TX("$60 per day")),
                            B("Rent now"), weights=[1, 2, 1], valign="center")),
                   CARD(ROW(IMG(110, "full", glyph="x", alt="ev"), COL(H("City EV", 3), TX("$75 per day")),
                            B("Reserve car"), weights=[1, 2, 1], valign="center")), gap=18),
               weights=[1, 3], gap=26), gap=22),
       "A car rental page with a navbar (DriveNow logo, Cars, Locations and a My trips button), a Filters card with "
       "SUV, Sedan and Electric checkboxes, a Pickup city field and an Apply button, and two car cards on the "
       "right: Urban SUV $60 per day with a Rent now button and City EV $75 per day with a Reserve car button. "
       "Rent now opens a Checkout page and Locations opens a Locations page.",
       [click("Rent now", type="navigate", page="Checkout"),
        click("Locations", type="navigate", page="Locations")])

# ---------------------------------------------------------------- contact
screen("hold_contact_01", "contact", "Feedback", MOBILE,
       COL(H("How did we do?", 1, "center"), RB("Great"), RB("Okay"), RB("Poor"),
           TA("Tell us more", 4), CB("You may contact me"), B("Send feedback", "full"), gap=16),
       "A feedback survey with the heading How did we do?, Great, Okay and Poor radio buttons, a Tell us more "
       "text area, a You may contact me checkbox and a full width Send feedback button. Send feedback shows the "
       "message Thanks for your feedback.",
       [click("Send feedback", type="show_message", text_contains="thanks for your feedback")])

screen("hold_contact_02", "contact", "Our offices", DESKTOP,
       COL(H("Our offices", 1),
           ROW(CARD(H("Hyderabad", 2), TX("Road 12, Banjara Hills"), L("Get directions")),
               CARD(H("Berlin", 2), TX("Torstrasse 4, Mitte"), L("Directions to Berlin")),
               CARD(H("Austin", 2), TX("200 Congress Avenue"), L("Directions to Austin")), gap=18),
           IMG(200, "full", glyph="mountain", alt="world map"),
           ROW(I("Your email", "email"), B("Request a call", 220), weights=[3, 1], gap=18), gap=22),
       "An offices page with the heading Our offices, three cards for Hyderabad, Berlin and Austin each with an "
       "address and a directions link (Get directions, Directions to Berlin, Directions to Austin), a wide world "
       "map image and a Your email field with a Request a call button. Request a call checks that the email is "
       "valid and Get directions opens a Map page.",
       [click("Request a call", type="validate_format", field_label="Your email", format="email"),
        click("Get directions", type="navigate", page="Map")])

# ---------------------------------------------------------------- settings
screen("hold_set_01", "settings", "Notifications", NARROW,
       COL(H("Notification preferences", 1),
           ROW(TX("Comments"), CB("Comments alerts", True), weights=[1, 2]),
           ROW(TX("Mentions"), CB("Mentions alerts", True), weights=[1, 2]),
           ROW(TX("Weekly digest"), CB("Digest email", True), weights=[1, 2]),
           SEL("Frequency", None, ["Instant", "Daily", "Weekly"]),
           ROW(B("Save preferences"), B("Reset", style="double"), weights=[1, 1], gap=20), gap=18),
       "A notification preferences page with the heading Notification preferences, three toggle rows for "
       "Comments alerts, Mentions alerts and Digest email, a Frequency dropdown (Instant, Daily, Weekly), and Save "
       "preferences and Reset buttons. Save preferences shows the message Preferences saved.",
       [click("Save preferences", type="show_message", text_contains="preferences saved")])

screen("hold_set_02", "settings", "Connected apps", DESKTOP,
       COL(H("Connected apps", 1),
           CARD(ROW(ICO("cloud"), TX("Drive sync"), B("Disconnect Drive", 220), weights=[1, 4, 3], valign="center")),
           CARD(ROW(ICO("mail"), TX("Mail import"), B("Disconnect Mail", 220), weights=[1, 4, 3], valign="center")),
           CARD(ROW(ICO("bolt"), TX("Automation hooks"), B("Disconnect Hooks", 220), weights=[1, 4, 3], valign="center")),
           DIV(),
           CARD(H("Danger zone", 2), TX("This cannot be undone"), B("Delete account", 220, style="double")), gap=18),
       "A connected apps settings page with the heading Connected apps, three cards Drive sync, Mail import and "
       "Automation hooks each with an icon and a Disconnect button (Disconnect Drive, Disconnect Mail, Disconnect "
       "Hooks), a divider and a Danger zone card with the text This cannot be undone and a Delete account button. "
       "Delete account shows the message Please confirm deletion.",
       [click("Delete account", type="show_message", text_contains="confirm deletion")])

# ---------------------------------------------------------------- landing
screen("hold_land_01", "landing", "Pasta House", DESKTOP,
       COL(NAV(left=[NI("Pasta House"), NI("Menu"), NI("Reserve")], right=[NI("Contact")]),
           IMG(260, "full", glyph="mountain", alt="restaurant banner"),
           H("Fresh pasta daily", 1, "center"), TX("Made by hand every morning", "center"),
           B("Order online", 240, "center"),
           ROW(CARD(IMG(110, "full", glyph="x", alt="carbonara"), TX("Carbonara")),
               CARD(IMG(110, "full", glyph="x", alt="pesto"), TX("Pesto")),
               CARD(IMG(110, "full", glyph="x", alt="lasagna"), TX("Lasagna")), gap=18), gap=18),
       "A restaurant landing page with a navbar (Pasta House logo, Menu, Reserve and Contact), a wide banner photo, "
       "the centered headline Fresh pasta daily, the line Made by hand every morning, an Order online button and "
       "three dish cards Carbonara, Pesto and Lasagna with photos. Order online opens an Order page and Reserve "
       "opens a Reservation page.",
       [click("Order online", type="navigate", page="Order"),
        click("Reserve", type="navigate", page="Reservation")])

screen("hold_land_02", "landing", "DevSummit", DESKTOP,
       COL(H("DevSummit 2027", 1, "center"), TX("12 to 14 March, Bengaluru", "center"),
           ROW(CARD(TX("Days"), H("12", 2)), CARD(TX("Hours"), H("04", 2)), CARD(TX("Minutes"), H("37", 2)),
               gap=18),
           H("Speakers", 2),
           ROW(COL(IMG(110, 110, shape="circle", alt="speaker"), TX("Asha Nair")),
               COL(IMG(110, 110, shape="circle", alt="speaker"), TX("Liam Chen")),
               COL(IMG(110, 110, shape="circle", alt="speaker"), TX("Sofia Alvarez")),
               COL(IMG(110, 110, shape="circle", alt="speaker"), TX("Ken Ito")), gap=18),
           B("Register now", 260, "center"),
           ROW(I("Get updates by email", "email"), B("Subscribe", 200), weights=[3, 1], gap=18), gap=20),
       "A conference landing page with the centered headline DevSummit 2027, the line 12 to 14 March, Bengaluru, a "
       "countdown of three cards Days, Hours and Minutes, a Speakers heading with four round photos named Asha "
       "Nair, Liam Chen, Sofia Alvarez and Ken Ito, a Register now button, and a Get updates by email field with "
       "a Subscribe button. Register now opens a Tickets page and Subscribe checks the email is valid.",
       [click("Register now", type="navigate", page="Tickets"),
        click("Subscribe", type="validate_format", field_label="Get updates by email", format="email")])
