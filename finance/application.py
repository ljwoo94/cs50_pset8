import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]
    cash = db.execute("SELECT cash FROM users WHERE id = :id", id=user_id)
    cash = cash[0]["cash"]
    history = db.execute("SELECT symbol, SUM(number) as n FROM history WHERE userid = :id GROUP BY symbol", id=user_id)

    total = round(cash, 2)
    table = {}
    for row in history:
        sym = row["symbol"]
        table[sym] = lookup(sym)
        total = total + table[sym]["price"] * row["n"]

    return render_template("index.html", table=table, history=history, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("No Symbol", 400)
        elif not request.form.get("shares"):
            return apology("No Numbers", 400)
        elif not request.form.get("shares").isdecimal():
            return apology("Please enter decimal number", 400)

        symbol = request.form.get("symbol")
        number = int(request.form.get("shares"))
        if number < 0:
            return apology("Positive number required", 400)

        quote = lookup(symbol)
        if quote == None:
            return apology("Symbol does not Exist", 400)
        user_id = session["user_id"]
        price = float(quote["price"]) * number
        price = round(price, 2)
        user_cash = db.execute("SELECT cash FROM users WHERE id = :id", id=user_id)
        cash = float(user_cash[0]["cash"])

        if cash < price:
            return apology("Not Enough Money", 400)

        db.execute("UPDATE users SET cash = cash - :price WHERE id = :id", price=price, id=user_id)
        db.execute("INSERT INTO history (userid, symbol, number, price) VALUES (" + str(user_id) + ", '" + symbol + "', " + str(number) + ", " + str(price) + ")")

        return render_template("bought.html", symbol=symbol, price=price, number=number)

    return render_template("buy.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    return jsonify("TODO")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT * FROM history WHERE userid =: id", id=session["user_id"])
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        quotes = lookup(request.form.get("symbol"))

        if quotes == None:
            return apology("No such symbol exists", 400)
        return render_template("quoted.html", data=quotes)

    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST" :

        if not request.form.get("username"):
            return apology("Must provide user name", 400)
        elif not request.form.get("password"):
            return apology("Must provide password", 400)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Password Confirmation Failed", 400)

        name = request.form.get("username")
        password = request.form.get("password")
        names = db.execute("SELECT username FROM users WHERE username = :username", username=name)

        if len(names) > 0:
            return apology("Username Already Exists", 400)

        hash_password = generate_password_hash(password)
        db.execute("INSERT INTO users(username, hash) Values( '"+ name + "', '" + hash_password + "')")
        return redirect("/login")
    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("Select the share to Sell", 400)
        if not request.form.get("shares"):
            return apology("Enter the number of shares to sell", 400)
        if not request.form.get("shares").isdigit():
            return apology("Invalid Number", 400)
        number = int(request.form.get("shares"))

        if number < 0:
            return apology("Positive please", 400)
        user_id = session["user_id"]
        symbol = request.form.get("symbol")
        history = db.execute("SELECT SUM(number) as n FROM history WHERE userid = :id AND symbol = :symbol", id=user_id, symbol=symbol)

        if number > int(history[0]["n"]):
            return apology("Do not have enough shares", 400)

        price = float(lookup(symbol)["price"])
        price *= number
        price = round(price, 2)
        command_price = str(price)
        command_num = str(number)
        db.execute("UPDATE users SET cash = cash + :price WHERE id = id", price = command_price, id=user_id)
        db.execute("INSERT INTO history (userid, symbol, number, price) VALUES (" + str(user_id) + ", '" + symbol + "', " + str(number) + ", " + str(price) + ")")
        return redirect("/")

    else:
        symbols = db.execute("SELECT symbol FROM history WHERE userid = :id GROUP BY symbol", id=session["user_id"])
        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
