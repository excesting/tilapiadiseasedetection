# populate_users.py
from yolo_app import app, db, UserLogin
from werkzeug.security import generate_password_hash

def populate_users():
    with app.app_context():
        # List of users to add
        users = [
            {'username': 'admin', 'password': 'admin123'},
            {'username': 'user1', 'password': 'user123'},
            {'username': 'user2', 'password': 'pass456'},
        ]

        for user in users:
            # Check if the user already exists
            existing_user = UserLogin.query.filter_by(username=user['username']).first()
            if existing_user:
                print(f"User {user['username']} already exists.")
                continue

            # Hash the password
            hashed_password = generate_password_hash(user['password'], method='pbkdf2:sha256')
            
            # Create a new user and save to the database
            new_user = UserLogin(username=user['username'], password=hashed_password)
            db.session.add(new_user)
        
        # Commit the changes to the database
        db.session.commit()

if __name__ == "__main__":
    populate_users()