from datetime import date
from pathlib import Path
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import Base, engine, session
from .models import Event, Player, Pod, Registration
from .services import create_round, load_event, standings

BASE=Path(__file__).parent
app=FastAPI(title="Command Zone",version="1.0.0")
app.mount("/static",StaticFiles(directory=BASE/"static"),name="static")
templates=Jinja2Templates(directory=BASE/"templates")

@app.on_event("startup")
def startup(): Base.metadata.create_all(engine)

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/")
def home(request:Request,event_id:str|None=None,db:Session=Depends(session)):
    parsed_event_id = int(event_id) if event_id and event_id.isdigit() else None
    event=load_event(db,parsed_event_id)
    players=db.scalars(select(Player).order_by(Player.name)).all()
    events=db.scalars(select(Event).order_by(Event.id.desc())).all()
    return templates.TemplateResponse(request,"index.html",{"event":event,"players":players,"events":events,"standing":standings(event) if event else []})

@app.post("/players")
def add_player(name:str=Form(),commander:str=Form(""),db:Session=Depends(session)):
    db.add(Player(name=name.strip(),commander=commander.strip()));db.commit();return RedirectResponse("/?tab=players",303)

@app.post("/players/{player_id}")
def edit_player(player_id:int,name:str=Form(),commander:str=Form(""),db:Session=Depends(session)):
    p=db.get(Player,player_id);p.name=name.strip();p.commander=commander.strip();db.commit();return RedirectResponse("/?tab=players",303)

@app.post("/events")
def add_event(name:str=Form(),event_date:date=Form(),player_ids:list[int]=Form(default=[]),db:Session=Depends(session)):
    event=Event(name=name.strip(),event_date=event_date);event.registrations=[Registration(player_id=x) for x in player_ids];db.add(event);db.commit();return RedirectResponse(f"/?event_id={event.id}",303)

@app.post("/events/{event_id}/toggle/{player_id}")
def toggle(event_id:int,player_id:int,db:Session=Depends(session)):
    reg=db.scalar(select(Registration).where(Registration.event_id==event_id,Registration.player_id==player_id))
    db.delete(reg) if reg else db.add(Registration(event_id=event_id,player_id=player_id));db.commit();return RedirectResponse(f"/?event_id={event_id}&tab=players",303)

@app.post("/events/{event_id}/rounds")
def round_create(event_id:int,db:Session=Depends(session)):
    event=load_event(db,event_id);create_round(db,event);return RedirectResponse(f"/?event_id={event_id}",303)

@app.post("/events/{event_id}/pods/{pod_id}/winner")
def winner(event_id:int,pod_id:int,player_id:int=Form(),db:Session=Depends(session)):
    pod=db.get(Pod,pod_id);pod.winner_id=player_id;db.commit();return RedirectResponse(f"/?event_id={event_id}",303)
