from datetime import date
from pathlib import Path
import os, secrets
from urllib.parse import urlencode
import httpx
from fastapi import Depends, FastAPI, Form, HTTPException, Request
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
        def columns(table):
            if engine.dialect.name=="sqlite": return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            return {row[0] for row in conn.exec_driver_sql("SELECT column_name FROM information_schema.columns WHERE table_name=%s",(table,))}
        if "deck" not in columns("seats"): conn.exec_driver_sql("ALTER TABLE seats ADD COLUMN deck VARCHAR(160) NOT NULL DEFAULT ''")
        if "active" not in columns("users"): conn.exec_driver_sql("ALTER TABLE users ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE")
        if "email" not in columns("users"): conn.exec_driver_sql("ALTER TABLE users ADD COLUMN email VARCHAR(255)")
        if "google_sub" not in columns("users"): conn.exec_driver_sql("ALTER TABLE users ADD COLUMN google_sub VARCHAR(255)")
        conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)")
        conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub ON users (google_sub)")
        if "draw" not in columns("pods"): conn.exec_driver_sql("ALTER TABLE pods ADD COLUMN draw BOOLEAN NOT NULL DEFAULT FALSE")

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/")
def home(request:Request,event_id:str|None=None,db:Session=Depends(session)):
    parsed_event_id = int(event_id) if event_id and event_id.isdigit() else None
    event=load_event(db,parsed_event_id) if parsed_event_id else None
    players=db.scalars(select(Player).order_by(Player.name)).all()
    events=db.scalars(select(Event).order_by(Event.id.desc())).all()
    user=current_user(request,db)
    users=db.scalars(select(User).order_by(User.username)).all() if user and user.role=="admin" else []
    return templates.TemplateResponse(request,"index.html",{"event":event,"players":players,"events":events,"users":users,"standing":standings(event) if event else [],"user":user,"needs_setup":db.scalar(select(User.id).limit(1)) is None,"error":request.query_params.get("error"),"primary_admin_email":os.getenv("PRIMARY_ADMIN_EMAIL","").strip().lower()})

@app.get("/login")
def login_page(request:Request,db:Session=Depends(session)):
    return templates.TemplateResponse(request,"login.html",{"setup":db.scalar(select(User.id).limit(1)) is None,"error":request.query_params.get("error"),"google_enabled":bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))})

@app.post("/setup")
def setup(request:Request,username:str=Form(),password:str=Form(),db:Session=Depends(session)):
    if db.scalar(select(User.id).limit(1)) is not None: raise HTTPException(404)
    if len(password)<8:return templates.TemplateResponse(request,"login.html",{"setup":True,"error":"Пароль должен содержать минимум 8 символов"},status_code=400)
    user=User(username=username.strip(),password_hash=hash_password(password),role="admin");db.add(user);db.commit();request.session["user_id"]=user.id
    return RedirectResponse("/",303)

@app.post("/login")
def login(request:Request,username:str=Form(),password:str=Form(),db:Session=Depends(session)):
    user=db.scalar(select(User).where(User.username==username.strip()))
    if not user or not user.active or not verify_password(password,user.password_hash):return templates.TemplateResponse(request,"login.html",{"setup":False,"error":"Неверный логин, пароль или аккаунт отключён","google_enabled":bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))},status_code=400)
    request.session["user_id"]=user.id;return RedirectResponse("/",303)

@app.post("/logout")
def logout(request:Request):request.session.clear();return RedirectResponse("/login",303)

@app.get("/auth/google")
def google_login(request:Request):
    client_id=os.getenv("GOOGLE_CLIENT_ID")
    if not client_id or not os.getenv("GOOGLE_CLIENT_SECRET"):return RedirectResponse("/login?error=Вход через Google ещё не настроен",303)
    state=secrets.token_urlsafe(32);request.session["google_oauth_state"]=state
    redirect_uri=os.getenv("GOOGLE_REDIRECT_URI",str(request.url_for("google_callback")))
    params={"client_id":client_id,"redirect_uri":redirect_uri,"response_type":"code","scope":"openid email profile","state":state,"prompt":"select_account"}
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?"+urlencode(params),303)

@app.get("/auth/google/callback")
async def google_callback(request:Request,code:str|None=None,state:str|None=None,error:str|None=None,db:Session=Depends(session)):
    expected=request.session.pop("google_oauth_state",None)
    if error:return RedirectResponse("/login?error=Вход через Google отменён",303)
    if not code or not state or not expected or not secrets.compare_digest(state,expected):return RedirectResponse("/login?error=Не удалось проверить вход через Google",303)
    redirect_uri=os.getenv("GOOGLE_REDIRECT_URI",str(request.url_for("google_callback")))
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_response=await client.post("https://oauth2.googleapis.com/token",data={"code":code,"client_id":os.environ["GOOGLE_CLIENT_ID"],"client_secret":os.environ["GOOGLE_CLIENT_SECRET"],"redirect_uri":redirect_uri,"grant_type":"authorization_code"})
            token_response.raise_for_status();access_token=token_response.json()["access_token"]
            info_response=await client.get("https://openidconnect.googleapis.com/v1/userinfo",headers={"Authorization":f"Bearer {access_token}"})
            info_response.raise_for_status();info=info_response.json()
    except (httpx.HTTPError,KeyError):return RedirectResponse("/login?error=Google не подтвердил вход",303)
    if not info.get("email_verified") or not info.get("email") or not info.get("sub"):return RedirectResponse("/login?error=Google-email не подтверждён",303)
    email=info["email"].strip().lower();sub=info["sub"]
    user=db.scalar(select(User).where((User.google_sub==sub)|(User.email==email)))
    if not user:return RedirectResponse("/login?error=Этот Google-аккаунт не добавлен администратором",303)
    if not user.active:return RedirectResponse("/login?error=Доступ для аккаунта отключён",303)
    if user.google_sub and user.google_sub!=sub:return RedirectResponse("/login?error=Email уже связан с другим Google-аккаунтом",303)
    user.google_sub=sub;user.email=email;db.commit();request.session["user_id"]=user.id
    return RedirectResponse("/",303)

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

@app.post("/users")
def create_user(request:Request,username:str=Form(),password:str=Form(),email:str=Form(""),role:str=Form("player"),player_id:str=Form(""),db:Session=Depends(session)):
    require_admin(request,db);username=username.strip()
    if not username:return RedirectResponse("/?tab=users&error=Укажите логин",303)
    if db.scalar(select(User.id).where(User.username==username)):return RedirectResponse("/?tab=users&error=Такой логин уже существует",303)
    if len(password)<8:return RedirectResponse("/?tab=users&error=Пароль должен содержать минимум 8 символов",303)
    email=email.strip().lower() or None
    if email and db.scalar(select(User.id).where(User.email==email)):return RedirectResponse("/?tab=users&error=Этот email уже используется",303)
    if role not in {"admin","player"}:raise HTTPException(400,"Неизвестная роль")
    linked_player_id=int(player_id) if player_id.isdigit() else None
    if linked_player_id and db.scalar(select(User.id).where(User.player_id==linked_player_id)):return RedirectResponse("/?tab=users&error=У этого игрока уже есть аккаунт",303)
    db.add(User(username=username,email=email,password_hash=hash_password(password),role=role,player_id=linked_player_id,active=True));db.commit()
    return RedirectResponse("/?tab=users",303)

@app.post("/users/{user_id}")
def edit_user(request:Request,user_id:int,role:str=Form(),player_id:str=Form(""),email:str=Form(""),password:str=Form(""),active:bool=Form(False),db:Session=Depends(session)):
    admin=require_admin(request,db);target=db.get(User,user_id)
    if not target:raise HTTPException(404)
    if role not in {"admin","player"}:raise HTTPException(400,"Неизвестная роль")
    email=email.strip().lower() or None
    primary_email=os.getenv("PRIMARY_ADMIN_EMAIL","").strip().lower()
    if primary_email and target.email==primary_email and (email!=primary_email or role!="admin" or not active):return RedirectResponse("/?tab=users&error=Главного администратора нельзя отключить, понизить или изменить его email",303)
    removing_admin=target.role=="admin" and target.active and (role!="admin" or not active)
    admin_count=len(db.scalars(select(User.id).where(User.role=="admin",User.active==True)).all())
    if removing_admin and admin_count<=1:return RedirectResponse("/?tab=users&error=Нельзя отключить или понизить последнего администратора",303)
    if target.id==admin.id and not active:return RedirectResponse("/?tab=users&error=Нельзя отключить собственный аккаунт",303)
    linked_player_id=int(player_id) if player_id.isdigit() else None
    owner=db.scalar(select(User).where(User.player_id==linked_player_id,User.id!=target.id)) if linked_player_id else None
    if owner:return RedirectResponse("/?tab=users&error=У этого игрока уже есть аккаунт",303)
    email_owner=db.scalar(select(User).where(User.email==email,User.id!=target.id)) if email else None
    if email_owner:return RedirectResponse("/?tab=users&error=Этот email уже используется",303)
    if password and len(password)<8:return RedirectResponse("/?tab=users&error=Новый пароль должен содержать минимум 8 символов",303)
    target.role=role;target.player_id=linked_player_id;target.email=email;target.active=active
    if password:target.password_hash=hash_password(password)
    db.commit();return RedirectResponse("/?tab=users",303)

@app.post("/events")
def add_event(request:Request,name:str=Form(),event_date:date=Form(),player_ids:list[int]=Form(default=[]),db:Session=Depends(session)):
    require_admin(request,db)
    event=Event(name=name.strip(),event_date=event_date);event.registrations=[Registration(player_id=x) for x in player_ids];db.add(event);db.commit();return RedirectResponse(f"/?event_id={event.id}",303)

@app.post("/events/{event_id}/toggle/{player_id}")
def toggle(request:Request,event_id:int,player_id:int,db:Session=Depends(session)):
    require_admin(request,db)
    event=db.get(Event,event_id)
    if not event or not db.get(Player,player_id):raise HTTPException(404)
    if not event.active:raise HTTPException(409,"Турнир завершён")
    reg=db.scalar(select(Registration).where(Registration.event_id==event_id,Registration.player_id==player_id))
    db.delete(reg) if reg else db.add(Registration(event_id=event_id,player_id=player_id));db.commit();return RedirectResponse(f"/?event_id={event_id}&tab=roster",303)

@app.post("/events/{event_id}/rounds")
def round_create(request:Request,event_id:int,db:Session=Depends(session)):
    require_admin(request,db)
    event=load_event(db,event_id)
    if not event or not event.active:raise HTTPException(409,"Турнир завершён")
    create_round(db,event);return RedirectResponse(f"/?event_id={event_id}",303)

@app.post("/events/{event_id}/finish")
def finish_event(request:Request,event_id:int,db:Session=Depends(session)):
    require_admin(request,db);event=db.get(Event,event_id)
    if not event:raise HTTPException(404)
    event.active=False;db.commit();return RedirectResponse(f"/?event_id={event_id}",303)

@app.post("/events/{event_id}/pods/{pod_id}/winner")
def winner(request:Request,event_id:int,pod_id:int,player_id:int=Form(),db:Session=Depends(session)):
    require_admin(request,db)
    event=load_event(db,event_id);pod=db.get(Pod,pod_id)
    if not event or not pod:raise HTTPException(404)
    if not event.active:raise HTTPException(409,"Турнир завершён")
    latest_round=event.rounds[-1] if event.rounds else None
    if not latest_round or pod.round_id!=latest_round.id:raise HTTPException(409,"Победителя можно выбирать только в текущем раунде")
    if player_id not in {seat.player_id for seat in pod.seats}:raise HTTPException(400,"Игрок не сидит за этим столом")
    pod.winner_id=player_id;pod.draw=False;db.commit();return RedirectResponse(f"/?event_id={event_id}",303)

@app.post("/events/{event_id}/pods/{pod_id}/draw")
def draw(request:Request,event_id:int,pod_id:int,db:Session=Depends(session)):
    require_admin(request,db)
    event=load_event(db,event_id);pod=db.get(Pod,pod_id)
    if not event or not pod:raise HTTPException(404)
    if not event.active:raise HTTPException(409,"Турнир завершён")
    latest_round=event.rounds[-1] if event.rounds else None
    if not latest_round or pod.round_id!=latest_round.id:raise HTTPException(409,"Ничью можно выбирать только в текущем раунде")
    pod.winner_id=None;pod.draw=True;db.commit();return RedirectResponse(f"/?event_id={event_id}",303)

@app.post("/events/{event_id}/seats/{seat_id}/deck")
def set_deck(request:Request,event_id:int,seat_id:int,deck:str=Form(""),db:Session=Depends(session)):
    user=current_user(request,db);seat=db.get(Seat,seat_id);event=db.get(Event,event_id)
    if not user:raise HTTPException(401)
    if not event or not event.active:raise HTTPException(409,"Турнир завершён")
    if user.role!="admin" and user.player_id!=seat.player_id:raise HTTPException(403)
    seat.deck=deck.strip();db.commit();return RedirectResponse(f"/?event_id={event_id}",303)
