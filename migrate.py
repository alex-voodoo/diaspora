#!./venv/bin/python

import os
import pathlib
import sqlite3


def main() -> None:
    conn = sqlite3.connect("people.db")
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS \"migrations\" ("
              "\"name\" TEXT UNIQUE,"
              "PRIMARY KEY(\"name\")"
              ")")

    migrations_directory = pathlib.Path(__file__).parent / "migrations"
    migration_filenames = sorted(filename for filename in os.listdir(migrations_directory) if filename.endswith(".txt"))
    for migration_filename in migration_filenames:
        skip = False
        for _ in c.execute("SELECT name FROM migrations WHERE name=?", (migration_filename,)):
            print("Migration {filename} is already applied, skipping".format(filename=migration_filename))
            skip = True

        if skip:
            continue

        with open(migrations_directory / migration_filename) as inp:
            migration = inp.read().split(";")
            for sql in migration:
                c.execute(sql)

            c.execute("INSERT INTO migrations(name) VALUES(?)", (migration_filename,))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
