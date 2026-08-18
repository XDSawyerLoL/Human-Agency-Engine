from app.db import SessionLocal
from app.services.cycle import AgencyCycle


def main() -> None:
    db = SessionLocal()
    try:
        result = AgencyCycle(db).run()
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
