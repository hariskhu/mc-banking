import pytest
from decimal import Decimal
from app.models.player import Player
from app.models.account import Account, AccountType

@pytest.mark.asyncio
async def test_get_balance(client, session):
    p = Player(discord_id="444", mc_username="dave")
    session.add(p)
    session.flush()
    session.add(Account(owner_type=AccountType.player, owner_id=p.id, balance=Decimal("75.00")))
    session.commit()

    response = await client.get("/accounts/444/balance")
    assert response.status_code == 200
    assert response.json()["balance"] == "75.00"

@pytest.mark.asyncio
async def test_get_balance_not_found(client):
    response = await client.get("/accounts/nonexistent/balance")
    assert response.status_code == 404