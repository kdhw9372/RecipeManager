-- Benutzer-Tabelle
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Kategorien-Tabelle
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rezepte-Tabelle
CREATE TABLE recipes (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    preparation_time INTEGER, -- in Minuten
    cooking_time INTEGER,     -- in Minuten
    servings INTEGER NOT NULL,
    difficulty VARCHAR(20),   -- z.B. leicht, mittel, schwer
    image_path VARCHAR(255),
    pdf_path VARCHAR(255),
    instructions TEXT NOT NULL,
    notes TEXT,
    is_favorite BOOLEAN DEFAULT FALSE,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rezept-Kategorie Zuordnung
CREATE TABLE recipe_categories (
    recipe_id INTEGER REFERENCES recipes(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (recipe_id, category_id)
);

-- Zutaten-Tabelle
CREATE TABLE ingredients (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    unit VARCHAR(20),         -- z.B. g, ml, TL, EL
    calories_per_unit NUMERIC(8, 2),
    protein_per_unit NUMERIC(8, 2),
    carbs_per_unit NUMERIC(8, 2),
    fat_per_unit NUMERIC(8, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rezept-Zutaten-Tabelle
CREATE TABLE recipe_ingredients (
    recipe_id INTEGER REFERENCES recipes(id) ON DELETE CASCADE,
    ingredient_id INTEGER REFERENCES ingredients(id) ON DELETE CASCADE,
    amount NUMERIC(8, 2) NOT NULL,
    unit VARCHAR(20),
    notes VARCHAR(255),
    PRIMARY KEY (recipe_id, ingredient_id)
);

-- Menüplan-Tabelle
CREATE TABLE meal_plans (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    meal_type VARCHAR(20) NOT NULL, -- z.B. Frühstück, Mittag, Abend
    recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
    servings INTEGER DEFAULT 1,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Einkaufslisten-Tabelle
CREATE TABLE shopping_lists (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Einkaufslisten-Einträge
CREATE TABLE shopping_list_items (
    id SERIAL PRIMARY KEY,
    shopping_list_id INTEGER REFERENCES shopping_lists(id) ON DELETE CASCADE,
    ingredient_id INTEGER REFERENCES ingredients(id) ON DELETE CASCADE,
    amount NUMERIC(8, 2) NOT NULL,
    unit VARCHAR(20),
    is_checked BOOLEAN DEFAULT FALSE,
    notes VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Nährwert-Tabelle für Rezepte
CREATE TABLE recipe_nutrition (
    recipe_id INTEGER REFERENCES recipes(id) ON DELETE CASCADE PRIMARY KEY,
    calories NUMERIC(8, 2),
    protein NUMERIC(8, 2),
    carbs NUMERIC(8, 2),
    fat NUMERIC(8, 2),
    fiber NUMERIC(8, 2),
    sugar NUMERIC(8, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Backup-Historie
CREATE TABLE backups (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    size BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);