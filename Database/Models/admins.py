default_admins = [
            (, ""),
            (768903494, "lisov18"),
            (, "")

for admin_id, username in default_admins:
    self.cursor.execute(
        "INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)",
        (admin_id, username)
    )

self.connection.commit()