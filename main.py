import os
from datetime import datetime
from fastapi import FastAPI, Depends, Form, File, HTTPException, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import Base, engine, get_db
from models import User, Capsule, Message
from schemas import UserCreate, UserOut, UserUpdate, Token, CapsuleOut, CapsuleCreate, MessageOut
from auth import hash_password, verify_password, create_access_token, get_current_user
from notification import send_sms, send_email
from utils import delete_file, upload_file
from typing import Optional

# ---------------------------
# Config
# ---------------------------
DEV_MODE = True

app = FastAPI(title="Capsule API")
Base.metadata.create_all(bind=engine)

os.makedirs(os.getenv("UPLOAD_DIR"), exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production, spécifiez vos domaines
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Users
# ---------------------------
@app.post("/users/", response_model=UserOut)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.phone == user.phone).first()
    if existing:
        raise HTTPException(status_code=400, detail="Téléphone déjà utilisé")

    hashed = hash_password(user.password)
    db_user = User(
        firstname=user.firstname,
        lastname=user.lastname,
        phone=user.phone,
        email=user.email,
        hashed_password=hashed,
        is_admin=user.is_admin if hasattr(user, "is_admin") else False
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Non autorisé")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return user


@app.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, update: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Non autorisé")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    if update.firstname is not None:
        user.firstname = update.firstname
    if update.lastname is not None:
        user.lastname = update.lastname
    if update.phone is not None:
        user.phone = update.phone
    if update.email is not None:
        user.email = update.email
    if update.password is not None:
        user.hashed_password = hash_password(update.password)
    if update.is_admin is not None and current_user.is_admin:
        user.is_admin = update.is_admin

    db.commit()
    db.refresh(user)
    return user


@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    # 🔹 Autorisation admin
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Non autorisé")

    db.delete(user)
    db.commit()
    return {"detail": f"Utilisateur {user_id} supprimé"}


# ---------------------------
# Auth
# ---------------------------
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

    recipient = db.query(User).filter(User.phone == capsule.recipient_phone).first()

    if capsule.notify_on_create:
        message = f"Une nouvelle capsule vous est destinée: {capsule.name}"
        if recipient:
            if DEV_MODE:
                print(f"[DEV] SMS to {capsule.recipient_phone}: {message}")
            else:
                background_tasks.add_task(send_sms, capsule.recipient_phone, message)
                if recipient.email:
                    background_tasks.add_task(send_email, recipient.email, "Nouvelle capsule", message)
        else:
            if DEV_MODE:
                print(f"[DEV] SMS to {capsule.recipient_phone}: {message}")
            else:
                background_tasks.add_task(send_sms, capsule.recipient_phone,
                    f"On vous a envoyé une capsule '{capsule.name}'. Téléchargez l'app pour la voir !")
    else:
        print(f"[TODO] Notification différée prévue pour le {capsule.reveal_date}")

    return db_capsule


@app.get("/capsules/{capsule_id}", response_model=CapsuleOut)
def get_capsule(
    capsule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    capsule = db.query(Capsule).filter(Capsule.id == capsule_id).first()
    if not capsule:
        raise HTTPException(status_code=404, detail="Capsule non trouvée")

    # Vérification accès à la capsule
    if not current_user.is_admin:
        if not (
            capsule.owner_id == current_user.id
            or capsule.recipient_phone == current_user.phone
        ):
            raise HTTPException(status_code=403, detail="Non autorisé à voir cette capsule")

    # Filtrage des messages selon l’accès
    messages_out = []
    for m in capsule.messages:
        if (
            current_user.is_admin
            or m.creator_id == current_user.id
            or (capsule.owner_id == current_user.id and capsule.reveal_date <= datetime.utcnow())
            or (capsule.recipient_phone == current_user.phone and capsule.reveal_date <= datetime.utcnow())
        ):
            messages_out.append(
                MessageOut(
                    id=m.id,
                    user_id=m.creator_id,
                    text=m.text,
                    filename=m.filename,
                    time=m.created_at
                )
            )

    return CapsuleOut(
        id=capsule.id,
        name=capsule.name,
        reveal_date=capsule.reveal_date,
        owner_id=capsule.owner_id,
        recipient_phone=capsule.recipient_phone,
        notify_on_create=capsule.notify_on_create,
        messages=messages_out
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

    if not (current_user.is_admin or capsule.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="Non autorisé à modifier cette capsule")

    if capsule.name is not None:        
        capsule.name = capsule_data.name
    if capsule.reveal_date is not None:     
        capsule.reveal_date = capsule_data.reveal_date
    if capsule.notify_on_create is not None: 
        capsule.notify_on_create = capsule_data.notify_on_create
    if capsule.recipient_phone is not None: 
        capsule.recipient_phone = capsule_data.recipient_phone

    db.commit()
    db.refresh(capsule)
    return capsule


@app.delete("/capsules/{capsule_id}")
def delete_capsule(capsule_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    capsule = db.query(Capsule).filter(Capsule.id == capsule_id).first()
    if not capsule:
        raise HTTPException(status_code=404, detail="Capsule non trouvée")

    if not (current_user.is_admin or capsule.owner_id == current_user.id):
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
def create_message(
    capsule_id: int,
    text: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Vérifie que le message n'est pas vide
    if not text and not file:
        raise HTTPException(status_code=422, detail="Le message doit contenir du texte ou un fichier")

    capsule = db.query(Capsule).filter(Capsule.id == capsule_id).first()
    if not capsule:
        raise HTTPException(status_code=404, detail="Capsule non trouvée")

    filepath = None
    if file:
        filepath = upload_file(file, os.getenv("UPLOAD_DIR"))

    msg = Message(
        text=text,
        filename=filepath,
        capsule_id=capsule_id,
        creator_id=current_user.id
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return MessageOut(
        id=msg.id,
        user_id=msg.creator_id,
        text=msg.text,
        filename=msg.filename,
        time=msg.created_at
    )


@app.get("/capsules/{capsule_id}/messages/{message_id}", response_model=MessageOut)
def get_message(
    capsule_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    msg = db.query(Message).filter(
        Message.id == message_id,
        Message.capsule_id == capsule_id
    ).first()

    if not msg:
        raise HTTPException(status_code=404, detail="Message non trouvé")

    capsule = db.query(Capsule).filter(Capsule.id == capsule_id).first()

    # Autorisation
    if not (
        current_user.is_admin
        or msg.creator_id == current_user.id
        or (capsule.owner_id == current_user.id and capsule.reveal_date <= datetime.utcnow())
        or (capsule.recipient_phone == current_user.phone and capsule.reveal_date <= datetime.utcnow())
    ):
        raise HTTPException(status_code=403, detail="Non autorisé à voir ce message")

    return MessageOut(
        id=msg.id,
        user_id=msg.creator_id,
        text=msg.text,
        filename=msg.filename,
        time=msg.created_at
    )


@app.put("/capsules/{capsule_id}/messages/{message_id}", response_model=MessageOut)
def update_message(
    capsule_id: int,
    message_id: int,
    text: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not text and not file:
        raise HTTPException(
            status_code=422,
            detail="Le message doit contenir du texte ou un fichier"
        )

    msg = db.query(Message).filter(
        Message.id == message_id,
        Message.capsule_id == capsule_id
    ).first()

    if not msg:
        raise HTTPException(status_code=404, detail="Message non trouvé")

    if msg.creator_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Non autorisé à modifier ce message")

    if text is not None:
        msg.text = text

    if file and file.filename != "":
        print("fichier uploadé mon cousin")
        if msg.filename:
            delete_file(msg.filename)
        msg.filename = upload_file(file, os.getenv("UPLOAD_DIR"))
    else:
        print("il a pas detecté de fichier mon cousin")
    

    db.commit()
    db.refresh(msg)

    return MessageOut(
        id=msg.id,
        user_id=msg.creator_id,
        text=msg.text,
        filename=msg.filename,
        time=msg.created_at
    )

@app.delete("/capsules/{capsule_id}/messages/{message_id}")
def delete_message(
    capsule_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    msg = db.query(Message).filter(
        Message.id == message_id,
        Message.capsule_id == capsule_id
    ).first()

    if not msg:
        raise HTTPException(status_code=404, detail="Message non trouvé")

    # Autorisation
    if not (
        current_user.is_admin
        or msg.creator_id == current_user.id
        or msg.capsule.owner_id == current_user.id
    ):
        raise HTTPException(status_code=403, detail="Non autorisé")

    # Supprimer le fichier associé s’il existe
    if msg.filename:
        delete_file(msg.filename)

    db.delete(msg)
    db.commit()
    return {"detail": f"Message {message_id} supprimé"}
