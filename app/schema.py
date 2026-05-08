import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn_string = os.getenv("DATABASE_URL")

SQL = """
DROP TABLE IF EXISTS deposits_and_withdrawals CASCADE;
DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS shop_items CASCADE;
DROP TABLE IF EXISTS shops CASCADE;
DROP TABLE IF EXISTS loans CASCADE;
DROP TABLE IF EXISTS guild_roles CASCADE;
DROP TABLE IF EXISTS exchange_rates CASCADE;
DROP TABLE IF EXISTS vault_inventory CASCADE;
DROP TABLE IF EXISTS players CASCADE;
DROP TABLE IF EXISTS guilds CASCADE;

DROP TYPE IF EXISTS guild_status CASCADE;
DROP TYPE IF EXISTS guild_role CASCADE;
DROP TYPE IF EXISTS loan_status CASCADE;
DROP TYPE IF EXISTS transaction_type CASCADE;
DROP TYPE IF EXISTS entity_type CASCADE;
DROP TYPE IF EXISTS ref_type CASCADE;
DROP TYPE IF EXISTS material CASCADE;

CREATE TYPE guild_status AS ENUM ('active', 'suspended', 'dissolved');
CREATE TYPE loan_status AS ENUM ('active', 'repaid', 'defaulted');
CREATE TYPE transaction_type AS ENUM (
    'deposit', 'withdrawal', 'transfer', 'shop_purchase',
    'loan_disbursement', 'loan_repayment',
    'treasury_contribution', 'treasury_withdrawal'
);
CREATE TYPE entity_type AS ENUM ('player', 'guild', 'bank');
CREATE TYPE guild_role AS ENUM ('captain', 'officer', 'member');
CREATE TYPE ref_type AS ENUM ('deposit_withdrawal', 'loan', 'shop_purchase');
CREATE TYPE material AS ENUM ('copper', 'iron', 'zinc', 'gold');

CREATE TABLE guilds (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    leader_id  TEXT NOT NULL,
    balance    NUMERIC(18, 2) DEFAULT 0,
    status     guild_status DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE players (
    id               SERIAL PRIMARY KEY,
    discord_id       TEXT NOT NULL UNIQUE,
    discord_username TEXT NOT NULL,
    mc_username      TEXT,
    guild_id         INT REFERENCES guilds (id) ON DELETE SET NULL,
    balance          NUMERIC(18, 2) DEFAULT 0,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE guilds
    ADD CONSTRAINT fk_guilds_leader
    FOREIGN KEY (leader_id) REFERENCES players (discord_id) ON DELETE RESTRICT;

CREATE TABLE guild_roles (
    id         SERIAL PRIMARY KEY,
    guild_id   INT NOT NULL REFERENCES guilds (id) ON DELETE CASCADE,
    player_id  INT NOT NULL REFERENCES players (id) ON DELETE CASCADE,
    role       guild_role NOT NULL,
    granted_by INT REFERENCES players (id) ON DELETE SET NULL,
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (guild_id, player_id)
);

CREATE TABLE vault_inventory (
    id         SERIAL PRIMARY KEY,
    material   material NOT NULL UNIQUE,
    quantity   INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE vault_inventory
ADD CONSTRAINT non_negative_quantity CHECK (quantity >= 0);

INSERT INTO vault_inventory (material, quantity) VALUES
    ('copper', 0), ('iron', 0), ('zinc', 0), ('gold', 0);

CREATE TABLE exchange_rates (
    id         SERIAL PRIMARY KEY,
    material   material NOT NULL,
    rate       NUMERIC(18, 2) NOT NULL,
    set_by     INT NOT NULL REFERENCES players (id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE loans (
    id            SERIAL PRIMARY KEY,
    guild_id      INT NOT NULL REFERENCES guilds (id) ON DELETE RESTRICT,
    principal     NUMERIC(18, 2) NOT NULL,
    borrowing_fee NUMERIC(18, 2) NOT NULL DEFAULT 0,
    amount_paid   NUMERIC(18, 2) NOT NULL DEFAULT 0,
    status        loan_status NOT NULL DEFAULT 'active',
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    due_at        TIMESTAMPTZ DEFAULT NOW() + INTERVAL '3 days'
);

CREATE TABLE shops (
    id         SERIAL PRIMARY KEY,
    guild_id   INT NOT NULL REFERENCES guilds (id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    active     BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE shop_items (
    id                  SERIAL PRIMARY KEY,
    shop_id             INT NOT NULL REFERENCES shops (id) ON DELETE CASCADE,
    item_name           TEXT NOT NULL,
    amount_per_purchase INT,
    price               NUMERIC(18, 2) NOT NULL,
    active              BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE transactions (
    id               SERIAL PRIMARY KEY,
    type             transaction_type NOT NULL,
    from_entity_type entity_type,
    from_entity_id   INT,
    to_entity_type   entity_type,
    to_entity_id     INT,
    amount           NUMERIC(18, 2) NOT NULL,
    fee_amount       NUMERIC(18, 2) NOT NULL DEFAULT 0,
    ref_id           INT,
    ref_type         ref_type,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE vault_inventory_log (
    id          SERIAL PRIMARY KEY,
    material    material NOT NULL,
    quantity    INT NOT NULL,
    delta       INT NOT NULL,
    reason      transaction_type,
    ref_tx_id   INT REFERENCES transactions(id),
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE deposits_and_withdrawals (
    id             SERIAL PRIMARY KEY,
    player_id      INT NOT NULL REFERENCES players (id) ON DELETE RESTRICT,
    rate_id        INT NOT NULL REFERENCES exchange_rates (id) ON DELETE RESTRICT,
    transaction_id INT NOT NULL UNIQUE REFERENCES transactions (id) ON DELETE RESTRICT,
    material       material NOT NULL,
    quantity       INT NOT NULL,
    value          NUMERIC(18, 2) NOT NULL,
    is_deposit     BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMPTZ DEFAULT NOW()

CREATE VIEW current_exchange_rates AS
SELECT DISTINCT ON (material) *
FROM exchange_rates
ORDER BY material, created_at DESC;

CREATE VIEW bank_liquidity AS
SELECT
    SUM(vi.quantity * cr.rate) AS total_vault_value,
    COALESCE((SELECT SUM(balance) FROM players), 0) +
    COALESCE((SELECT SUM(balance) FROM guilds), 0) AS total_account_balances,

    SUM(vi.quantity * cr.rate) - (
        COALESCE((SELECT SUM(balance) FROM players), 0) +
        COALESCE((SELECT SUM(balance) FROM guilds), 0)
    ) AS excess_supply,

    (SUM(vi.quantity * cr.rate) - (
        COALESCE((SELECT SUM(balance) FROM players), 0) +
        COALESCE((SELECT SUM(balance) FROM guilds), 0)
    )) * 0.8 AS loanable_funds

FROM vault_inventory vi
JOIN current_exchange_rates cr ON cr.material = vi.material;
"""

try:
    with psycopg2.connect(conn_string) as conn:
        print("Connection established.")
        with conn.cursor() as cur:
            cur.execute(SQL)
        print("Schema created successfully.")
except Exception as e:
    print("Failed to create schema.")
    print(e)