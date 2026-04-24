CREATE DATABASE IF NOT EXISTS subsy_db;
USE subsy_db;

DROP TABLE IF EXISTS subscriptions;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(80) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE subscriptions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) DEFAULT 'Streaming',
    price DECIMAL(10,2) NOT NULL,
    billing_cycle ENUM('monthly', 'yearly') DEFAULT 'monthly',
    renewal_day INT NOT NULL,
    start_date DATE NULL,
    notes TEXT NULL,
    is_active TINYINT(1) DEFAULT 1,
    color VARCHAR(20) DEFAULT '#38bdf8',
    icon VARCHAR(50) DEFAULT '📺',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);