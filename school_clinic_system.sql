-- Create the database
CREATE DATABASE school_clinic_system;
USE school_clinic_system;

-- 1. USERS table
CREATE TABLE users (
    user_id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    email VARCHAR(100),
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    birthdate DATE,
    age INT,
    gender ENUM('Male', 'Female', 'Other'),
    address TEXT,
    phone_number VARCHAR(20),
    role ENUM('student', 'parent', 'staff', 'admin'),
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    guardian_id INT,
    student_ref_id INT,
    profile_photo TEXT,
    emergency_contact_name VARCHAR(100),
    emergency_contact_phone VARCHAR(20),
    school_id VARCHAR(20),
    last_login DATETIME,
    FOREIGN KEY (guardian_id) REFERENCES users(user_id),
    FOREIGN KEY (student_ref_id) REFERENCES users(user_id)
);
INSERT INTO users (
    username,
    password,
    email,
    first_name,
    last_name,
    birthdate,
    age,
    gender,
    address,
    phone_number,
    role,
    is_active,
    guardian_id,
    student_ref_id,
    profile_photo,
    emergency_contact_name,
    emergency_contact_phone,
    school_id,
    last_login
) VALUES (
    'cyberghost_admin',
    'p@ssw0rd123',  -- Not hashed, per instruction
    'reddevcm3era@gmail.com',
    'Eli',
    'Hunter',
    '1990-10-31',
    34,
    'Other',
    'Unknown Facility, Cyber Defense HQ, Darknet Sector 7',
    '+639191234567',
    'admin',
    TRUE,
    NULL,
    NULL,
    'cyberghost.png',  -- Could be a cool hacker-themed avatar
    'Zero Day',
    '+639188765432',
    'CYB3R-SCH-001',
    NOW()
);

-- 2. HEALTH_RECORDS table
CREATE TABLE health_records (
    record_id INT PRIMARY KEY AUTO_INCREMENT,
    student_id INT,
    recorded_by INT,
    height_cm DECIMAL(5,2),
    weight_kg DECIMAL(5,2),
    blood_type VARCHAR(3),
    allergies TEXT,
    medical_conditions TEXT,
    current_medications TEXT,
    immunization_status TEXT,
    vision_test_result VARCHAR(100),
    hearing_test_result VARCHAR(100),
    general_diagnosis TEXT,
    treatment_plan TEXT,
    doctor_notes TEXT,
    visit_date DATE,
    next_follow_up DATE,
    status ENUM('Active', 'Resolved', 'Archived'),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES users(user_id),
    FOREIGN KEY (recorded_by) REFERENCES users(user_id)
);

-- 3. APPOINTMENTS table
CREATE TABLE appointments (
    appointment_id INT PRIMARY KEY AUTO_INCREMENT,
    student_id INT,
    booked_by INT,
    staff_id INT,
    appointment_date DATE,
    appointment_time TIME,
    appointment_type VARCHAR(100),
    reason TEXT,
    symptoms TEXT,
    diagnosis TEXT,
    treatment TEXT,
    prescription TEXT,
    follow_up_needed BOOLEAN,
    follow_up_date DATE,
    status ENUM('Pending', 'Completed', 'Cancelled'),
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    reminder_sent BOOLEAN DEFAULT FALSE,
    reschedule_count INT DEFAULT 0,
    FOREIGN KEY (student_id) REFERENCES users(user_id),
    FOREIGN KEY (booked_by) REFERENCES users(user_id),
    FOREIGN KEY (staff_id) REFERENCES users(user_id)
);

-- 4. VACCINATIONS table
CREATE TABLE vaccinations (
    vaccination_id INT PRIMARY KEY AUTO_INCREMENT,
    student_id INT,
    vaccine_name VARCHAR(100),
    vaccine_type VARCHAR(100),
    manufacturer VARCHAR(100),
    batch_number VARCHAR(50),
    dose_number INT,
    total_doses INT,
    date_administered DATE,
    next_due_date DATE,
    administered_by INT,
    site_of_injection VARCHAR(100),
    side_effects TEXT,
    status ENUM('Completed', 'Pending'),
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    approved_by INT,
    consent_required BOOLEAN,
    parent_consent BOOLEAN,
    FOREIGN KEY (student_id) REFERENCES users(user_id),
    FOREIGN KEY (administered_by) REFERENCES users(user_id),
    FOREIGN KEY (approved_by) REFERENCES users(user_id)
);

-- 5. NOTIFICATIONS table
CREATE TABLE notifications (
    notification_id INT PRIMARY KEY AUTO_INCREMENT,
    recipient_id INT,
    sender_id INT,
    message_type ENUM('Alert', 'Reminder', 'Report', 'Info'),
    subject VARCHAR(100),
    message TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    read_at DATETIME,
    related_record_id INT,
    appointment_id INT,
    urgent BOOLEAN DEFAULT FALSE,
    delivery_method ENUM('Email', 'SMS', 'In-App'),
    expiry_date DATETIME,
    attachment_url TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    resend_attempts INT DEFAULT 0,
    parent_id INT,
    FOREIGN KEY (recipient_id) REFERENCES users(user_id),
    FOREIGN KEY (sender_id) REFERENCES users(user_id),
    FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id),
    FOREIGN KEY (parent_id) REFERENCES users(user_id)
);
ALTER TABLE health_records ADD COLUMN last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;