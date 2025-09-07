import os, uuid, shutil
from datetime import datetime
from fastapi import FastAPI, Depends, Form, HTTPException, UploadFile, BackgroundTasks
from sqlalchemy.orm import Session
from database import Base, engine, get_db
from models import User, Capsule, Message
from schemas import UserCreate, UserOut, Token, CapsuleOut, CapsuleCreate, MessageOut
from auth import hash_password, verify_password, create_access_token, get_current_user
from notification import send_sms, send_email

# ---------------------------
# Config
# ---------------------------
DEV_MODE = True

app = FastAPI(title="Capsule API")
Base.metadata.create_all(bind=engine)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------------------
# Auth
# ---------------------------
@app.post("/register", response_model=UserOut)
def register(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter((User.phone == user.phone) | (User.email == user.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Téléphone ou email déjà utilisé")

    hashed = hash_password(user.password)
    db_user = User(
        firstname=user.firstname,
        lastname=user.lastname,
        phone=user.phone,
        email=user.email,
        hashed_password=hashed
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/login", response_model=Token)
def login(phone: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone == phone).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Numéro ou mot de passe invalide")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user
    
# ---------------------------
# Capsules
# ---------------------------
@app.post("/capsules/", response_model=CapsuleOut)
def create_capsule(
    capsule: CapsuleCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_capsule = Capsule(
        name=capsule.name,
        reveal_date=capsule.reveal_date,
        owner_id=current_user.id,
        notify_on_create=capsule.notify_on_create,
        recipient_phone=capsule.recipient_phone
    )
    db.add(db_capsule)
    db.commit()
    db.refresh(db_capsule)

    # ---------------------------
    # Notifications
    # ---------------------------
    recipient = db.query(User).filter(User.phone == capsule.recipient_phone).first()

    if capsule.notify_on_create:
        message = f"Une nouvelle capsule vous est destinée: {capsule.name}"
        if recipient:
            if DEV_MODE:
                print(f"[DEV] SMS to {capsule.recipient_phone}: {message}")
            else:
                # L’utilisateur existe déjà → notif SMS + Email
                background_tasks.add_task(
                    send_sms,
                    capsule.recipient_phone,
                    message
                )
                if recipient.email:
                    background_tasks.add_task(
                        send_email,
                        recipient.email,
                        "Nouvelle capsule",
                        message
                    )
        else:
            if DEV_MODE:
                print(f"[DEV] SMS to {capsule.recipient_phone}: {message}")
            else:
                # L’utilisateur n’existe pas → SMS d’invitation
                background_tasks.add_task(
                    send_sms,
                    capsule.recipient_phone,
                    f"On vous a envoyé une capsule '{capsule.name}'. Téléchargez l'app pour la voir !"
                )
    else:
        # 🔹 Sinon: notification seulement à la reveal_date (à planifier)
        print(f"[TODO] Notification différée prévue pour le {capsule.reveal_date}")

    return db_capsule

@app.get("/capsules/{capsule_id}", response_model=CapsuleOut)
def get_capsule(capsule_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    capsule = db.query(Capsule).filter(Capsule.id == capsule_id).first()
    if not capsule:
        raise HTTPException(status_code=404, detail="Capsule non trouvée")

    messages = []
    for m in capsule.messages:
        if (
            m.creator_id == current_user.id or
            (capsule.owner_id == current_user.id and capsule.reveal_date <= datetime.utcnow()) or
            (capsule.recipient_phone == current_user.phone and capsule.reveal_date <= datetime.utcnow())
        ):
            messages.append(m)

    return CapsuleOut(
        id=capsule.id,
        name=capsule.name,
        reveal_date=capsule.reveal_date,
        owner_id=capsule.owner_id,
        recipient_phone=capsule.recipient_phone,
        notify_on_create=capsule.notify_on_create,
        messages=[
            MessageOut(
                id=m.id,
                user_id=m.creator_id,
                url=m.filename,
                time=m.created_at
            ) for m in messages
        ]
    )
@app.put("/capsules/{capsule_id}", response_model=CapsuleOut)
def update_capsule(
    capsule_id: int,
    capsule_data: CapsuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    capsule = db.query(Capsule).filter(Capsule.id == capsule_id).first()
    if not capsule:
        raise HTTPException(status_code=404, detail="Capsule non trouvée")
    if capsule.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Non autorisé à modifier cette capsule")

    capsule.name = capsule_data.name
    capsule.reveal_date = capsule_data.reveal_date
    capsule.notify_on_create = capsule_data.notify_on_create
    capsule.recipient_phone = capsule_data.recipient_phone

    db.commit()
    db.refresh(capsule)
    return capsule


@app.delete("/capsules/{capsule_id}")
def delete_capsule(capsule_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    capsule = db.query(Capsule).filter(Capsule.id == capsule_id).first()
    if not capsule:
        raise HTTPException(status_code=404, detail="Capsule non trouvée")
    if capsule.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Non autorisé")

    for msg in capsule.messages:
        if os.path.exists(msg.filename):
            os.remove(msg.filename)

    db.delete(capsule)
    db.commit()
    return {"detail": f"Capsule {capsule_id} supprimée"}

# ---------------------------
# Messages
# ---------------------------
@app.post("/capsules/{capsule_id}/messages/", response_model=MessageOut)
def create_message(capsule_id: int, file: UploadFile, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    capsule = db.query(Capsule).filter(Capsule.id == capsule_id).first()
    if not capsule:
        raise HTTPException(status_code=404, detail="Capsule non trouvée")

    filename = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    msg = Message(
        filename=filepath,
        capsule_id=capsule_id,
        creator_id=current_user.id
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return MessageOut(id=msg.id, user_id=msg.creator_id, url=msg.filename, time=msg.created_at)

@app.get("/capsules/{capsule_id}/messages/{message_id}", response_model=MessageOut)
def get_message(capsule_id: int, message_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    msg = db.query(Message).filter(Message.id == message_id, Message.capsule_id == capsule_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message non trouvé")
    capsule = db.query(Capsule).filter(Capsule.id == capsule_id).first()
    if msg.creator_id != current_user.id and (capsule.owner_id != current_user.id or capsule.reveal_date > datetime.utcnow()):
        raise HTTPException(status_code=403, detail="Non autorisé à voir ce message")
    return MessageOut(id=msg.id, user_id=msg.creator_id, url=msg.filename, time=msg.created_at)

@app.put("/capsules/{capsule_id}/messages/{message_id}", response_model=MessageOut)
def update_message(capsule_id: int, message_id: int, file: UploadFile, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    msg = db.query(Message).filter(Message.id == message_id, Message.capsule_id == capsule_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message non trouvé")
    if msg.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Non autorisé à modifier ce message")

    # Supprimer l'ancien fichier
    if os.path.exists(msg.filename):
        os.remove(msg.filename)

    filename = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    msg.filename = filepath

    db.commit()
    db.refresh(msg)
    return MessageOut(id=msg.id, user_id=msg.creator_id, url=msg.filename, time=msg.created_at)

@app.delete("/capsules/{capsule_id}/messages/{message_id}")
def delete_message(capsule_id: int, message_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    msg = db.query(Message).filter(Message.id == message_id, Message.capsule_id == capsule_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message non trouvé")
    if msg.creator_id != current_user.id and msg.capsule.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Non autorisé")

    if os.path.exists(msg.filename):
        os.remove(msg.filename)

    db.delete(msg)
    db.commit()
    return {"detail": f"Message {message_id} supprimé"}
