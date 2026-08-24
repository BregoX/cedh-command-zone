from datetime import date
from pathlib import Path
import os
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import Base, engine, session
from .models import Event, Player, Pod, Registration, Seat, User
from .auth import current_user, hash_password, require_admin, verify_password
from .services import create_round, load_event, standings

BASE=Path(__file__).parent
app=FastAPI(title="Command Zone",version="1.0.0")
app.add_middleware(SessionMiddleware,secret_key=os.getenv("SECRET_KEY","local-development-secret-change-me"),same_site="lax",https_only=os.getenv("RENDER") is not None)
app.mount("/static",StaticFiles(directory=BASE/"static"),name="static")
templates=Jinja2Templates(directory=BASE/"templates")

@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        columns={row[1] for row in conn.exec_driver_sql("PRAGMA table_info(seats)")} if engine.dialect.name=="sqlite" else {row[0] for row in conn.exec_driver_sql("SELECT column_name FROM information_schema.columns WHERE table_name='seats'")}
        if "deck" not in columns: conn.exec_driver_sql("ALTER TABLE seats ADD COLUMN deck VARCHAR(160) NOT NULL DEFAULT ''")

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/")
def home(request:Request,event_id:str|None=None,db:Session=Depends(session)):
    parsed_event_id = int(event_id) if event_id and event_id.isdigit() else None
    event=load_event(db,parsed_event_id)
    players=db.scalars(select(Player).order_by(Player.name)).all()
    events=db.scalars(select(Event).order_by(Event.id.desc())).all()
    user=current_user(request,db)
    return templates.TemplateResponse(request,"index.html",{"event":event,"players":players,"events":events,"standing":standings(event) if event else [],"user":user,"needs_setup":db.scalar(select(User.id).limit(1)) is None})

@app.get("/login")
def login_page(request:Request,db:Session=Depends(session)):
    return templates.TemplateResponse(request,"login.html",{"setup":db.scalar(select(User.id).limit(1)) is None,"error":None})

@app.post("/setup")
def setup(request:Request,username:str=Form(),password:str=Form(),db:Session=Depends(session)):
    if db.scalar(select(User.id).limit(1)) is not None: raise HTTPException(404)
    if len(password)<8:return templates.TemplateResponse(request,"login.html",{"setup":True,"error":"Пароль должен содержать минимум 8 символов"},status_code=400)
    user=User(username=username.strip(),password_hash=hash_password(password),role="admin");db.add(user);db.commit();request.session["user_id"]=user.id
    return RedirectResponse("/",303)

@app.post("/login")
def login(request:Request,username:str=Form(),password:str=Form(),db:Session=Depends(session)):
    user=db.scalar(select(User).where(User.username==username.strip()))
    if not user or not verify_password(password,user.password_hash):return templates.TemplateResponse(request,"login.html",{"setup":False,"error":"Неверный логин или пароль"},status_code=400)
    request.session["user_id"]=user.id;return RedirectResponse("/",303)

@app.post("/logout")
def logout(request:Request):request.session.clear();return RedirectResponse("/login",303)

@app.post("/players")
def add_player(request:Request,name:str=Form(),commander:str=Form(""),db:Session=Depends(session)):
    require_admin(request,db)
    db.add(Player(name=name.strip(),commander=commander.strip()));db.commit();return RedirectResponse("/?tab=players",303)

@app.post("/players/{player_id}")
def edit_player(request:Request,player_id:int,name:str=Form(),commander:str=Form(""),db:Session=Depends(session)):
    require_admin(request,db)
    p=db.get(Player,player_id);p.name=name.strip();p.commander=commander.strip();db.commit();return RedirectResponse("/?tab=players",303)

@app.post("/players/{player_id}/account")
def create_player_account(request:Request,player_id:int,username:str=Form(),password:str=Form(),db:Session=Depends(session)):
    require_admin(request,db)
    if len(password)<8:raise HTTPException(400,"Пароль должен содержать минимум 8 символов")
    db.add(User(username=username.strip(),password_hash=hash_password(password),role="player",player_id=player_id));db.commit();return RedirectResponse("/?tab=players",303)

@app.post("/events")
def add_event(request:Request,name:str=Form(),event_date:date=Form(),player_ids:list[int]=Form(default=[]),db:Session=Depends(session)):
    require_admin(request,db)
    event=Event(name=name.strip(),event_date=event_date);event.registrations=[Registration(player_id=x) for x in player_ids];db.add(event);db.commit();return RedirectResponse(f"/?event_id={event.id}",303)

@app.post("/events/{event_id}/toggle/{player_id}")
def toggle(request:Request,event_id:int,player_id:int,db:Session=Depends(session)):
    require_admin(request,db)
    reg=db.scalar(select(Registration).where(Registration.event_id==event_id,Registration.player_id==player_id))
    db.delete(reg) if reg else db.add(Registration(event_id=event_id,player_id=player_id));db.commit();return RedirectResponse(f"/?event_id={event_id}&tab=players",303)

@app.post("/events/{event_id}/rounds")
def round_create(request:Request,event_id:int,db:Session=Depends(session)):
    require_admin(request,db)
    event=load_event(db,event_id);create_round(db,event);return RedirectResponse(f"/?event_id={event_id}",303)

@app.post("/events/{event_id}/pods/{pod_id}/winner")
def winner(request:Request,event_id:int,pod_id:int,player_id:int=Form(),db:Session=Depends(session)):
    require_admin(request,db)
    pod=db.get(Pod,pod_id);pod.winner_id=player_id;db.commit();return RedirectResponse(f"/?event_id={event_id}",303)

@app.post("/events/{event_id}/seats/{seat_id}/deck")
def set_deck(request:Request,event_id:int,seat_id:int,deck:str=Form(""),db:Session=Depends(session)):
    user=current_user(request,db);seat=db.get(Seat,seat_id)
    if not user:raise HTTPException(401)
    if user.role!="admin" and user.player_id!=seat.player_id:raise HTTPException(403)
    seat.deck=deck.strip();db.commit();return RedirectResponse(f"/?event_id={event_id}",303)
