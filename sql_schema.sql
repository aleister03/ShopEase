CREATE DATABASE ShopEaseDB;
USE ShopEaseDB;
CREATE TABLE Users (
    userID INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    phone VARCHAR(15) NOT NULL,
    password VARCHAR(255) NOT NULL,
    role ENUM('customer', 'seller', 'admin') DEFAULT 'customer',
    status ENUM('active', 'banned') DEFAULT 'active',
    address TEXT NOT NULL,
    joinDate DATE NOT NULL DEFAULT (CURDATE()),
    loyaltyPoints INT DEFAULT 0 CHECK (loyaltyPoints >= 0),
    
    INDEX idx_email (email),
    INDEX idx_role (role),
    INDEX idx_status (status)
);

CREATE TABLE Products (
    productID INT AUTO_INCREMENT PRIMARY KEY,
    productName VARCHAR(255) NOT NULL,
    productCategory VARCHAR(100) NOT NULL,
    brand VARCHAR(100) NOT NULL,
    dateAdded DATE NOT NULL DEFAULT (CURDATE()),
    
    INDEX idx_category (productCategory),
    INDEX idx_brand (brand),
    INDEX idx_date_added (dateAdded)
);

CREATE TABLE Inventory (
    inventoryID INT AUTO_INCREMENT PRIMARY KEY,
    productID INT NOT NULL,
    sellerID INT NOT NULL,
    pricePerUnit DECIMAL(10,2) NOT NULL CHECK (pricePerUnit > 0),
    currentStock INT NOT NULL DEFAULT 0 CHECK (currentStock >= 0),
    reorderLevel INT DEFAULT 10 CHECK (reorderLevel >= 0),
    
    FOREIGN KEY (productID) REFERENCES Products(productID) ON DELETE CASCADE,
    FOREIGN KEY (sellerID) REFERENCES Users(userID) ON DELETE CASCADE,
    
    UNIQUE KEY unique_seller_product (sellerID, productID),
    INDEX idx_product_inventory (productID),
    INDEX idx_seller_inventory (sellerID),
    INDEX idx_stock_level (currentStock)
);

CREATE TABLE Orders (
    orderID INT AUTO_INCREMENT PRIMARY KEY,
    userID INT NOT NULL,
    orderDate DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    orderStatus ENUM('pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled') DEFAULT 'pending',
    
    FOREIGN KEY (userID) REFERENCES Users(userID) ON DELETE CASCADE,
    INDEX idx_user_order (userID),
    INDEX idx_order_date (orderDate),
    INDEX idx_order_status (orderStatus)
);

CREATE TABLE Discounts (
    discountID INT AUTO_INCREMENT PRIMARY KEY,
    discountCode VARCHAR(50) UNIQUE NOT NULL,
    discountType ENUM('percentage', 'fixed_amount') NOT NULL,
    discountValue DECIMAL(10,2) NOT NULL CHECK (discountValue > 0),
    startDate DATE NOT NULL,
    endDate DATE NOT NULL,
    useLimit INT DEFAULT NULL,
    
    CHECK (endDate >= startDate),
    INDEX idx_discount_code (discountCode),
    INDEX idx_discount_dates (startDate, endDate)
);

CREATE TABLE OrderItems (
    orderID INT NOT NULL,
    inventoryID INT NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    priceOnSale DECIMAL(10,2) NOT NULL CHECK (priceOnSale > 0),
    discountID INT NULL,
    
    PRIMARY KEY (orderID, inventoryID),
    
    FOREIGN KEY (orderID) REFERENCES Orders(orderID) ON DELETE CASCADE,
    FOREIGN KEY (inventoryID) REFERENCES Inventory(inventoryID) ON DELETE RESTRICT,
    FOREIGN KEY (discountID) REFERENCES Discounts(discountID) ON DELETE SET NULL,
    
    INDEX idx_discount_usage (discountID)
);

CREATE TABLE Cart (
    userID INT NOT NULL,
    inventoryID INT NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    dateAdded DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    PRIMARY KEY (userID, inventoryID),
    
    FOREIGN KEY (userID) REFERENCES Users(userID) ON DELETE CASCADE,
    FOREIGN KEY (inventoryID) REFERENCES Inventory(inventoryID) ON DELETE CASCADE,
    
    INDEX idx_cart_date (dateAdded)
);

CREATE TABLE Payments (
    orderID INT NOT NULL,
    transactionDate DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    amount DECIMAL(10,2) NOT NULL CHECK (amount > 0),
    paymentMethod ENUM('cash_on_delivery') DEFAULT 'cash_on_delivery',
    paymentStatus ENUM('pending', 'completed', 'failed') DEFAULT 'pending',
    
    PRIMARY KEY (orderID, transactionDate),
    
    FOREIGN KEY (orderID) REFERENCES Orders(orderID) ON DELETE CASCADE,
    
    INDEX idx_payment_status (paymentStatus),
    INDEX idx_order_payment (orderID)
);

CREATE TABLE ProductReview (
    userID INT NOT NULL,
    productID INT NOT NULL,
    feedbackDate DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
    review TEXT,

    PRIMARY KEY (userID, productID, feedbackDate),
    
    FOREIGN KEY (userID) REFERENCES Users(userID) ON DELETE CASCADE,
    FOREIGN KEY (productID) REFERENCES Products(productID) ON DELETE CASCADE,
    
    INDEX idx_product_reviews (productID),
    INDEX idx_user_reviews (userID),
    INDEX idx_rating (rating),
    INDEX idx_review_date (feedbackDate)
);

CREATE TABLE Wishlist (
    userID INT NOT NULL,
    productID INT NOT NULL,
    dateAdded DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    PRIMARY KEY (userID, productID),
    
    FOREIGN KEY (userID) REFERENCES Users(userID) ON DELETE CASCADE,
    FOREIGN KEY (productID) REFERENCES Products(productID) ON DELETE CASCADE,
    
    INDEX idx_wishlist_date (dateAdded)
);

CREATE TABLE UserActivity (
    userID INT NOT NULL,
    inventoryID INT NOT NULL,
    activityType ENUM('purchase', 'view', 'wishlist') NOT NULL,
    activityDate DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    PRIMARY KEY (userID, inventoryID, activityType, activityDate),
    
    FOREIGN KEY (userID) REFERENCES Users(userID) ON DELETE CASCADE,
    FOREIGN KEY (inventoryID) REFERENCES Inventory(inventoryID) ON DELETE CASCADE,
    
    INDEX idx_activity_type (activityType),
    INDEX idx_user_activity (userID, activityDate),
    INDEX idx_inventory_activity (inventoryID, activityDate)

);
