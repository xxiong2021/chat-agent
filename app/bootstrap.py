import argparse
from app.core.auth import UserStore
parser = argparse.ArgumentParser(description="Create a Company Agent user")
parser.add_argument("username"); parser.add_argument("password"); parser.add_argument("--admin", action="store_true")
args = parser.parse_args(); UserStore().create_user(args.username, args.password, "admin" if args.admin else "employee")
print("User created.")
