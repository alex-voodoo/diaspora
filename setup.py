import os.path
import sqlite3


def main() -> None:
    if os.path.exists("secret.py") or os.path.exists("people.db"):
        print("ERROR: local files already exist!  Please remove secret.py and people.db before running this script.")
        return

    # Create secret.py
    token = input("Please enter your bot's token: ")

    secret_lines = (
        "BOT_TOKEN = \"{token}\"\n".format(token=token),
        "DEVELOPER_CHAT_ID = 0\n"
        "MAIN_CHAT_ID = 0\n"
    )
    with open("secret.py", "w") as secret:
        secret.writelines(secret_lines)
    print("- Created secret.py: bot configuration")

    # Create people.db
    conn = sqlite3.connect("people.db")
    c = conn.cursor()

    c.execute("CREATE TABLE \"people\" ("
              "\"tg_id\" INTEGER,"
              "\"tg_username\" TEXT,"
              "\"occupation\" TEXT,"
              "\"location\" TEXT,"
              "\"last_modified\" DATETIME DEFAULT CURRENT_TIMESTAMP,"
              "PRIMARY KEY(\"tg_id\"))")

    conn.commit()
    conn.close()

    print("- Created people.db: the empty database")

    print("The minimal setup is complete.  Refer to README.md for more information.")

if __name__ == "__main__":
    main()
