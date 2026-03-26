import sys
import traceback
from app import app, get_db

app.config['LOGIN_DISABLED'] = True

class MockUser:
    is_authenticated = True
    is_active = True
    is_anonymous = False
    barbearia_id = 1
    def get_id(self): return '1'

@app.login_manager.request_loader
def load_user_from_request(request):
    return MockUser()

with app.test_client() as c:
    for route in ['/api/dashboard', '/api/clientes']:
        print(f"\\n--- Testing {route} ---")
        try:
            res = c.get(route)
            print("Status:", res.status_code)
            if res.status_code == 500:
                print("500 Error Data:", res.data.decode('utf-8'))
        except Exception as e:
            traceback.print_exc()
