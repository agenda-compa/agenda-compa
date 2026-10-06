from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3, os, json, urllib.parse
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'agenda-compa-dev-2026')
DB = os.path.join(os.path.dirname(__file__), 'agenda_compa.db')


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    con.executescript('''
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL, adult_name TEXT, adult_contact TEXT, points INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS subjects(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT, teacher TEXT, schedule TEXT);
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT, kind TEXT, due TEXT, done INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS absences(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, date TEXT, reason TEXT);
    CREATE TABLE IF NOT EXISTS ideas(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, text TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS gatherings(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT, date TEXT, place TEXT, notes TEXT);
    CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, concept TEXT, amount REAL, date TEXT);
    CREATE TABLE IF NOT EXISTS auxilio(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, created TEXT, message TEXT, reference_id INTEGER, latitude REAL, longitude REAL, maps_url TEXT, whatsapp_url TEXT);
    CREATE TABLE IF NOT EXISTS emergency_references(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, name TEXT NOT NULL, relationship TEXT, phone TEXT NOT NULL, created TEXT, UNIQUE(user_id, phone));
    CREATE TABLE IF NOT EXISTS rewards(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, category TEXT, description TEXT, points INTEGER, date TEXT, place TEXT, stock INTEGER DEFAULT 0, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS redemptions(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, reward_id INTEGER, status TEXT DEFAULT 'Pendiente', created TEXT);
    CREATE TABLE IF NOT EXISTS surveys(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT, active INTEGER DEFAULT 1, created TEXT);
    CREATE TABLE IF NOT EXISTS survey_responses(id INTEGER PRIMARY KEY AUTOINCREMENT, survey_id INTEGER NOT NULL, answers TEXT NOT NULL, created TEXT);
    CREATE TABLE IF NOT EXISTS conflict_reports(id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, description TEXT NOT NULL, frequency TEXT, affected TEXT, proposal TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS proposals(id INTEGER PRIMARY KEY AUTOINCREMENT, conflict_id INTEGER, text TEXT NOT NULL, created TEXT);
    CREATE TABLE IF NOT EXISTS proposal_votes(id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id INTEGER NOT NULL, vote INTEGER NOT NULL, created TEXT);
    ''')
    # Migration for databases created by V3.
    cols = {r['name'] for r in con.execute('PRAGMA table_info(auxilio)').fetchall()}
    for name, typ in [('reference_id','INTEGER'),('latitude','REAL'),('longitude','REAL'),('maps_url','TEXT'),('whatsapp_url','TEXT')]:
        if name not in cols:
            con.execute(f'ALTER TABLE auxilio ADD COLUMN {name} {typ}')
    if con.execute('SELECT COUNT(*) FROM rewards').fetchone()[0] == 0:
        now = datetime.now().strftime('%Y-%m-%d')
        con.executemany('INSERT INTO rewards(title,category,description,points,date,place,stock) VALUES(?,?,?,?,?,?,?)', [
          ('Obra de teatro', 'Cultura', 'Entrada para una propuesta teatral.', 200, now, 'A confirmar', 20),
          ('Tarde de juegos', 'Recreación', 'Actividad recreativa y juegos.', 120, now, 'Espacio comunitario', 30),
          ('Visita cultural', 'Cultura', 'Museo, muestra o espacio cultural.', 180, now, 'A confirmar', 15),
          ('Actividad deportiva', 'Recreación', 'Experiencia deportiva grupal.', 150, now, 'A confirmar', 25),
        ])
    if con.execute('SELECT COUNT(*) FROM surveys').fetchone()[0] == 0:
        con.execute('INSERT INTO surveys(title,description,active,created) VALUES(?,?,1,?)', (
            '¿Cómo está el curso?', 'Contanos cómo estás viviendo el estudio. La respuesta es anónima y se usa solamente para detectar necesidades y buscar soluciones.', datetime.now().strftime('%Y-%m-%d %H:%M')))
    con.commit(); con.close()


@app.context_processor
def common():
    if 'user_id' in session:
        con = db(); user = con.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
        if user is None:
            con.close(); session.clear(); return {'current_user': None, 'absence_count': 0}
        absences = con.execute('SELECT COUNT(*) c FROM absences WHERE user_id=?', (session['user_id'],)).fetchone()['c']
        refs = con.execute('SELECT * FROM emergency_references WHERE user_id=? ORDER BY id', (session['user_id'],)).fetchall()
        con.close(); return {'current_user': user, 'absence_count': absences, 'emergency_references': refs}
    return {'current_user': None, 'absence_count': 0, 'emergency_references': []}


def participation_data(con):
    surveys = con.execute('SELECT * FROM surveys WHERE active=1 ORDER BY id DESC').fetchall(); survey_stats=[]
    for s in surveys:
        rows=con.execute('SELECT answers FROM survey_responses WHERE survey_id=?',(s['id'],)).fetchall(); counts={}
        for row in rows:
            try: answers=json.loads(row['answers'])
            except Exception: answers={}
            for k,v in answers.items():
                vals=v if isinstance(v,list) else [v]
                for val in vals:
                    if val: counts.setdefault(k,{})[val]=counts.setdefault(k,{}).get(val,0)+1
        survey_stats.append({'survey':s,'total':len(rows),'counts':counts})
    conflicts=con.execute('SELECT * FROM conflict_reports ORDER BY id DESC LIMIT 30').fetchall(); cards=[]
    for c in conflicts:
        n=con.execute('SELECT COUNT(*) FROM proposals WHERE conflict_id=?',(c['id'],)).fetchone()[0]
        cards.append({'row':c,'proposal_count':n})
    return survey_stats,cards


def require_login():
    return 'user_id' in session


@app.route('/')
def home():
    if not require_login(): return redirect(url_for('login'))
    con=db(); valid=con.execute('SELECT id FROM users WHERE id=?',(session['user_id'],)).fetchone()
    if not valid: con.close(); session.clear(); return redirect(url_for('login'))
    subjects=con.execute('SELECT * FROM subjects WHERE user_id=? ORDER BY name',(session['user_id'],)).fetchall()
    tasks=con.execute('SELECT * FROM tasks WHERE user_id=? ORDER BY due',(session['user_id'],)).fetchall()
    ideas=con.execute('SELECT * FROM ideas WHERE user_id=? ORDER BY id DESC',(session['user_id'],)).fetchall()
    gatherings=con.execute('SELECT * FROM gatherings WHERE user_id=? ORDER BY date',(session['user_id'],)).fetchall()
    expenses=con.execute('SELECT * FROM expenses WHERE user_id=? ORDER BY date DESC',(session['user_id'],)).fetchall()
    rewards=con.execute('SELECT * FROM rewards WHERE active=1 ORDER BY category,points').fetchall()
    red=con.execute('SELECT r.*, w.title, w.points FROM redemptions r JOIN rewards w ON w.id=r.reward_id WHERE r.user_id=? ORDER BY r.id DESC',(session['user_id'],)).fetchall()
    refs=con.execute('SELECT * FROM emergency_references WHERE user_id=? ORDER BY id',(session['user_id'],)).fetchall()
    aux=con.execute('SELECT a.*, e.name reference_name FROM auxilio a LEFT JOIN emergency_references e ON e.id=a.reference_id WHERE a.user_id=? ORDER BY a.id DESC LIMIT 10',(session['user_id'],)).fetchall()
    survey_stats, conflict_cards=participation_data(con); con.close()
    return render_template('index.html', subjects=subjects,tasks=tasks,ideas=ideas,gatherings=gatherings,expenses=expenses,rewards=rewards,redemptions=red,survey_stats=survey_stats,conflict_cards=conflict_cards,refs=refs,auxilios=aux)


@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        name=request.form['name'].strip(); email=request.form['email'].strip().lower(); password=request.form['password']; adult=request.form.get('adult_name','').strip(); contact=request.form.get('adult_contact','').strip()
        try:
            con=db(); cur=con.execute('INSERT INTO users(name,email,password,adult_name,adult_contact) VALUES(?,?,?,?,?)',(name,email,password,adult,contact)); con.commit(); session['user_id']=cur.lastrowid; con.close(); flash('Cuenta creada. ¡Bienvenido/a a Agenda Compa!'); return redirect(url_for('home'))
        except sqlite3.IntegrityError: flash('Ese correo ya está registrado.')
    return render_template('register.html')

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        con=db(); u=con.execute('SELECT * FROM users WHERE email=? AND password=?',(request.form['email'].strip().lower(),request.form['password'])).fetchone(); con.close()
        if u: session['user_id']=u['id']; return redirect(url_for('home'))
        flash('Usuario o contraseña incorrectos.')
    return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.post('/subject')
def subject():
    con=db(); con.execute('INSERT INTO subjects(user_id,name,teacher,schedule) VALUES(?,?,?,?)',(session['user_id'],request.form['name'],request.form.get('teacher',''),request.form.get('schedule',''))); con.commit(); con.close(); return redirect(url_for('home')+'#estudio')
@app.post('/task')
def task():
    con=db(); con.execute('INSERT INTO tasks(user_id,title,kind,due) VALUES(?,?,?,?)',(session['user_id'],request.form['title'],request.form['kind'],request.form.get('due',''))); con.commit(); con.close(); return redirect(url_for('home')+'#estudio')
@app.post('/task/<int:tid>/toggle')
def toggle_task(tid):
    con=db(); con.execute('UPDATE tasks SET done=1-done WHERE id=? AND user_id=?',(tid,session['user_id'])); con.commit(); con.close(); return redirect(url_for('home')+'#estudio')
@app.post('/absence')
def absence():
    con=db(); con.execute('INSERT INTO absences(user_id,date,reason) VALUES(?,?,?)',(session['user_id'],request.form.get('date') or datetime.now().strftime('%Y-%m-%d'),request.form.get('reason',''))); con.commit(); con.close(); return redirect(url_for('home')+'#estudio')
@app.post('/idea')
def idea():
    con=db(); con.execute('INSERT INTO ideas(user_id,text,created) VALUES(?,?,?)',(session['user_id'],request.form['text'],datetime.now().strftime('%Y-%m-%d %H:%M'))); con.commit(); con.close(); return redirect(url_for('home')+'#ideas')
@app.post('/gathering')
def gathering():
    con=db(); con.execute('INSERT INTO gatherings(user_id,title,date,place,notes) VALUES(?,?,?,?,?)',(session['user_id'],request.form['title'],request.form.get('date',''),request.form.get('place',''),request.form.get('notes',''))); con.commit(); con.close(); return redirect(url_for('home')+'#juntadas')
@app.post('/expense')
def expense():
    con=db(); con.execute('INSERT INTO expenses(user_id,concept,amount,date) VALUES(?,?,?,?)',(session['user_id'],request.form['concept'],float(request.form['amount']),request.form.get('date') or datetime.now().strftime('%Y-%m-%d'))); con.commit(); con.close(); return redirect(url_for('home')+'#gastos')

@app.post('/referentes/add')
def add_reference():
    name=request.form.get('name','').strip(); relationship=request.form.get('relationship','').strip(); phone=request.form.get('phone','').strip()
    if not name or not phone: flash('Completá nombre y teléfono del referente.'); return redirect(url_for('home')+'#auxilio')
    con=db(); count=con.execute('SELECT COUNT(*) FROM emergency_references WHERE user_id=?',(session['user_id'],)).fetchone()[0]
    if count>=3: con.close(); flash('Podés guardar hasta 3 referentes de emergencia.'); return redirect(url_for('home')+'#auxilio')
    try:
        con.execute('INSERT INTO emergency_references(user_id,name,relationship,phone,created) VALUES(?,?,?,?,?)',(session['user_id'],name,relationship,phone,datetime.now().strftime('%Y-%m-%d %H:%M'))); con.commit(); flash('Referente agregado.')
    except sqlite3.IntegrityError: flash('Ese teléfono ya está cargado como referente.')
    con.close(); return redirect(url_for('home')+'#auxilio')

@app.post('/referentes/<int:rid>/delete')
def delete_reference(rid):
    con=db(); con.execute('DELETE FROM emergency_references WHERE id=? AND user_id=?',(rid,session['user_id'])); con.commit(); con.close(); flash('Referente eliminado.'); return redirect(url_for('home')+'#auxilio')

@app.post('/auxilio')
def auxilio():
    rid=request.form.get('reference_id',type=int); lat=request.form.get('latitude',type=float); lon=request.form.get('longitude',type=float); message=request.form.get('message','Necesito ayuda').strip()
    con=db(); ref=con.execute('SELECT * FROM emergency_references WHERE id=? AND user_id=?',(rid,session['user_id'])).fetchone() if rid else None
    user=con.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
    if not ref: con.close(); return jsonify({'ok':False,'error':'Seleccioná un referente válido.'}),400
    maps_url=f'https://www.google.com/maps?q={lat},{lon}' if lat is not None and lon is not None else ''
    full=f'🚨 AUXILIO – Necesito ayuda.\nSoy {user["name"]}, estudiante de Agenda Compa.\n'
    if maps_url: full += f'Mi ubicación actual: {maps_url}\n'
    full += 'Por favor comunicate conmigo.'
    phone=''.join(ch for ch in ref['phone'] if ch.isdigit())
    if phone.startswith('0'): phone='54'+phone[1:]
    whatsapp_url='https://wa.me/'+phone+'?text='+urllib.parse.quote(full)
    now=datetime.now().strftime('%Y-%m-%d %H:%M')
    con.execute('INSERT INTO auxilio(user_id,created,message,reference_id,latitude,longitude,maps_url,whatsapp_url) VALUES(?,?,?,?,?,?,?,?)',(session['user_id'],now,full,ref['id'],lat,lon,maps_url,whatsapp_url)); con.commit(); con.close()
    return jsonify({'ok':True,'whatsapp_url':whatsapp_url,'maps_url':maps_url,'message':full,'reference':ref['name']})

@app.post('/survey/<int:sid>/answer')
def answer_survey(sid):
    con=db(); survey=con.execute('SELECT * FROM surveys WHERE id=? AND active=1',(sid,)).fetchone()
    if not survey: con.close(); flash('La encuesta no está disponible.'); return redirect(url_for('home'))
    answers={'situacion':request.form.get('situacion',''),'problema':request.form.get('problema',''),'frecuencia':request.form.get('frecuencia',''),'solucion':request.form.get('solucion','')}
    con.execute('INSERT INTO survey_responses(survey_id,answers,created) VALUES(?,?,?)',(sid,json.dumps(answers,ensure_ascii=False),datetime.now().strftime('%Y-%m-%d %H:%M'))); con.commit(); con.close(); flash('Respuesta recibida en modo incógnito. Gracias por ayudar a mejorar el curso.'); return redirect(url_for('home')+'#participacion')
@app.post('/conflict')
def conflict():
    category=request.form.get('category','Otro').strip(); description=request.form.get('description','').strip()
    if not description: flash('Contanos brevemente cuál es el problema.'); return redirect(url_for('home')+'#participacion')
    con=db(); con.execute('INSERT INTO conflict_reports(category,description,frequency,affected,proposal,created) VALUES(?,?,?,?,?,?)',(category,description,request.form.get('frequency',''),request.form.get('affected',''),request.form.get('proposal',''),datetime.now().strftime('%Y-%m-%d %H:%M'))); con.commit(); con.close(); flash('Situación registrada de forma anónima.'); return redirect(url_for('home')+'#participacion')
@app.post('/conflict/<int:cid>/proposal')
def proposal(cid):
    text=request.form.get('text','').strip()
    if text:
        con=db(); exists=con.execute('SELECT id FROM conflict_reports WHERE id=?',(cid,)).fetchone()
        if exists: con.execute('INSERT INTO proposals(conflict_id,text,created) VALUES(?,?,?)',(cid,text,datetime.now().strftime('%Y-%m-%d %H:%M'))); con.commit()
        con.close()
    return redirect(url_for('home')+'#participacion')
@app.post('/proposal/<int:pid>/vote')
def vote(pid):
    v=int(request.form.get('vote',1)); v=v if v in (1,-1) else 1; con=db(); con.execute('INSERT INTO proposal_votes(proposal_id,vote,created) VALUES(?,?,?)',(pid,v,datetime.now().strftime('%Y-%m-%d %H:%M'))); con.commit(); con.close(); return redirect(url_for('home')+'#participacion')
@app.post('/redeem/<int:rid>')
def redeem(rid):
    con=db(); u=con.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone(); r=con.execute('SELECT * FROM rewards WHERE id=? AND active=1',(rid,)).fetchone()
    if not r: flash('La experiencia no está disponible.')
    elif u['points']<r['points']: flash('No tenés suficientes puntos para este intercambio.')
    elif r['stock']<=0: flash('No quedan cupos disponibles.')
    else:
        con.execute('UPDATE users SET points=points-? WHERE id=?',(r['points'],u['id'])); con.execute('UPDATE rewards SET stock=stock-1 WHERE id=?',(rid,)); con.execute('INSERT INTO redemptions(user_id,reward_id,status,created) VALUES(?,?,?,?)',(u['id'],rid,'Pendiente de aprobación adulta',datetime.now().strftime('%Y-%m-%d %H:%M'))); con.commit(); flash('Solicitud de intercambio enviada para aprobación adulta.')
    con.close(); return redirect(url_for('home')+'#puntos')
@app.post('/points/add')
def add_points():
    amount=int(request.form['amount'])
    if amount<0 or amount>1000: flash('Cantidad no válida.')
    else:
        con=db(); con.execute('UPDATE users SET points=points+? WHERE id=?',(amount,session['user_id'])); con.commit(); con.close(); flash('Puntos agregados para la prueba del prototipo.')
    return redirect(url_for('home')+'#puntos')

if __name__=='__main__':
    init_db(); app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=True)
