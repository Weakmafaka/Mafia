import logging

from Database.database import logger


def _create_tables(self) -> None:
    try:
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT COLLATE NOCASE,
            first_name TEXT,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_premium BOOLEAN DEFAULT 0,
            premium_until TIMESTAMP,
            payment_method_id TEXT,
            trial_used BOOLEAN DEFAULT 0,
            age_group TEXT,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            permissions_level INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        self.connection.commit()

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS age_selection_stats (
                age_group TEXT PRIMARY KEY,
                selection_count INTEGER DEFAULT 0
            )
            ''')

        for age_group in ["0-3", "4-6", "7-10"]:
            self.cursor.execute(
                "INSERT OR IGNORE INTO age_selection_stats (age_group, selection_count) VALUES (?, 0)",
                (age_group,)
            )
        self.connection.commit()

        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            currency TEXT,
            status TEXT,
            payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_recurring BOOLEAN DEFAULT 0,
            description TEXT,
            payment_method_id TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')

        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_usage (
            user_id INTEGER,
            usage_date DATE,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, usage_date),
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')

        # Проверяем, существует ли столбец last_activity
        self.cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in self.cursor.fetchall()]
        if "last_activity" not in columns:
            self.cursor.execute("ALTER TABLE users ADD COLUMN last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
        default_admins = [
            (1692506573, "lenamalchevskaya"),
            (768903494, "lisov18"),
            (989687907, "vvv_valeria")
        ]

        for admin_id, username in default_admins:
            self.cursor.execute(
                "INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)",
                (admin_id, username)
            )

        self.connection.commit()

        # Таблица для подарочных подписок
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS gift_subscriptions (
            gift_code TEXT PRIMARY KEY,
            sender_id INTEGER NOT NULL,
            is_redeemed BOOLEAN DEFAULT 0,
            redeemed_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            redeemed_at TIMESTAMP
        )
        """)
        self.connection.commit()

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS locked_categories (
                category_name TEXT PRIMARY KEY
            )
            ''')
        self.connection.commit()

        logger.info("tables_created_successfully")
    except None as e:
        logger.error("table_creation_failed", error=str(e))
        raise