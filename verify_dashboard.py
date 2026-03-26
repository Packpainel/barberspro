import sys
import os
from datetime import date, timedelta
from app import app, get_db

app.config['LOGIN_DISABLED'] = True

class MockUser:
    is_authenticated = True
    barbearia_id = 1
    nome = "Test Admin"
    is_admin = True
    def get_id(self): return "1"

@app.login_manager.request_loader
def load_user(request):
    return MockUser()

with app.app_context():
    db = get_db()
    # Ensure barbearia exists
    db.execute("INSERT OR IGNORE INTO barbearias (id, nome, codigo) VALUES (1, 'Test Shop', 'TEST12')")
    # Add an inactive client (last visit 40 days ago)
    long_ago = (date.today() - timedelta(days=40)).isoformat()
    db.execute("INSERT INTO clientes (barbearia_id, nome, telefone, ultima_visita) VALUES (1, 'Client Inactive', '11999999999', ?)", (long_ago,))
    # Add a client who never visited (NULL ultima_visita) but was created long ago
    db.execute("INSERT INTO clientes (barbearia_id, nome, telefone, ultima_visita) VALUES (1, 'Client Never visited', '11888888888', NULL)")
    db.commit()
    db.close()

with app.test_client() as c:
    res = c.get('/api/dashboard')
    print("Dashboard Data:", res.get_json())
