from app.db import SessionLocal
from app.models import User
from app.services.engine import OpportunityEngine


def main() -> None:
    db = SessionLocal()
    try:
        service = OpportunityEngine(db)
        created = 0
        for user in db.query(User).all():
            created += len(service.run_for_user(user))
        print(f"created_opportunities={created}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
