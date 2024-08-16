CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- House Member table structure
CREATE TABLE house_members (
    id uuid PRIMARY KEY,
    last_name TEXT NOT NULL,
    first_name TEXT NOT NULL,
    parsed_doc_ids TEXT[] DEFAULT array[]::varchar[]
);

-- PTR table domains
-- S (partial) = Partial Sale in digital return
CREATE DOMAIN transaction_type AS TEXT
CHECK(
    VALUE IN (
        'P', -- Purchase
        'S', -- Sale
        'PS', -- Partial Sale
        'E' -- Exchange
    )
);

CREATE DOMAIN amount AS TEXT
CHECK(
    VALUE IN (
        'A', -- $1,001 - $15,000
        'B', -- $15,001 - $50,000
        'C', -- $50,001 - $100,000
        'D', -- $100,001 - $250,000
        'E', -- $250,001 - $500,000
        'F', -- $500,001 - $1,000,000
        'G', -- $1,000,001 - $5,000,000
        'H', -- $5,000,001 - $25,000,000
        'I', -- $25,000,001 - $50,000,000
        'J', -- $50,000,001 +
        'K' -- Transaction in a Spouse or Dependent Child Asset over $1,000,000
    )
);

-- PTR table structure
CREATE TABLE ptr (
    house_member_id uuid REFERENCES house_members(id),
    id TEXT PRIMARY KEY,
    asset TEXT NOT NULL,
    transaction_type transaction_type NOT NULL,
    transaction_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    notification_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    amount amount NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (current_timestamp AT TIME ZONE 'utc')
);

-- known reporting years table structure
CREATE TABLE known_years (
    year_id INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (current_timestamp AT TIME ZONE 'utc')
);

INSERT INTO known_years (year_id) VALUES (2013);
