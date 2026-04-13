import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from fastapi import Request
from app.main import app
from app.utils.middlewares import authen_restricted
from app.schemas.user import UserResponse

_MOCK_USER = UserResponse(
    id=1,
    name='Test User',
    email='test@test.com',
    phone='0123456789',
    chat_id='',
    stocks=['VGI', 'VNM'],
)

async def _mock_authen(request: Request):
    request.state.user = _MOCK_USER

app.dependency_overrides[authen_restricted] = _mock_authen
client = TestClient(app)


def test_get_me_returns_current_user():
    response = client.get('/user/me')
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == 1
    assert data['email'] == 'test@test.com'
    assert 'VGI' in data['stocks']


@patch('app.routers.user.remove_stock_from_user')
def test_remove_stock_calls_service_with_correct_args(mock_remove):
    mock_remove.return_value = UserResponse(
        id=1, name='Test User', email='test@test.com',
        phone='0123456789', chat_id='', stocks=['VNM'],
    )
    response = client.request('DELETE', '/user/remove_stock', content=json.dumps({'symbol': 'VGI'}), headers={'Content-Type': 'application/json'})
    assert response.status_code == 200
    mock_remove.assert_called_once_with(user_id=1, stock_symbol='VGI')


@patch('app.routers.user.remove_stock_from_user')
def test_remove_stock_returns_updated_stocks(mock_remove):
    mock_remove.return_value = UserResponse(
        id=1, name='Test User', email='test@test.com',
        phone='0123456789', chat_id='', stocks=['VNM'],
    )
    response = client.request('DELETE', '/user/remove_stock', content=json.dumps({'symbol': 'VGI'}), headers={'Content-Type': 'application/json'})
    data = response.json()
    assert 'VGI' not in data['stocks']
    assert 'VNM' in data['stocks']
