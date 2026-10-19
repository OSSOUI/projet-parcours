extends Node2D
## Campus de Tessaline en direct.
## Les donnees arrivent de pont.py par WebSocket. Rien n'est calcule ici :
## la scene AFFICHE, elle ne simule pas.
##
## Clic sur un etudiant : sa memoire et la justification de sa derniere
## decision (exigence D2). Boutons en bas : injection d'un evenement dans
## le monde en cours (exigence D3).

const URL := "ws://localhost:8765"
const RAYON := 22.0

# Une couleur par sens possible du ruban. C'est la lecture principale de
# la scene : la couleur dit ce que le ruban VEUT DIRE pour cet etudiant.
var COULEURS := {
	"cercle_creatif": Color("#7b5cd6"),
	"tendance": Color("#2a9d8f"),
	"suivre_la_foule": Color("#e9a23b"),
	"ringard": Color("#c8553d"),
	"ironie": Color("#3d7cc8"),
	"aucun_sens": Color("#9a97a6"),
}
const LIBELLES := {
	"cercle_creatif": "cercle creatif", "tendance": "tendance",
	"suivre_la_foule": "suit la foule", "ringard": "ringard",
	"ironie": "ironie", "aucun_sens": "aucun sens",
}
var FOND := Color("#f7f6fa")
var ENCRE := Color("#24212e")
var DOUX := Color("#64607a")
var TRAIT := Color("#dcd8e6")
const PANNEAU_X := 920.0

var ws := WebSocketPeer.new()
var connecte := false
var delai_reco := 0.0
var etat := {}
var positions := {}
var zones := {}
var selection := ""
var police: Font
var boutons := []


func _ready() -> void:
	police = ThemeDB.fallback_font
	_poser_boutons()
	ws.connect_to_url(URL)


func _poser_boutons() -> void:
	var noms := [
		{"titre": "Relais massif", "nature": "relais_massif"},
		{"titre": "Tendance rivale", "nature": "tendance_rivale"},
		{"titre": "Rumeur", "nature": "message"},
		{"titre": "Cloisonner", "nature": "cloisonnement"},
	]
	var x := 30.0
	for n in noms:
		boutons.append({"titre": n["titre"], "nature": n["nature"],
			"rect": Rect2(x, 722, 196, 36)})
		x += 210.0


func _process(delta: float) -> void:
	ws.poll()
	var s := ws.get_ready_state()
	if s == WebSocketPeer.STATE_OPEN:
		connecte = true
		while ws.get_available_packet_count() > 0:
			_recevoir(ws.get_packet().get_string_from_utf8())
	elif s == WebSocketPeer.STATE_CLOSED:
		connecte = false
		delai_reco -= delta
		if delai_reco <= 0.0:
			delai_reco = 2.0
			ws = WebSocketPeer.new()
			ws.connect_to_url(URL)
	queue_redraw()


func _recevoir(brut: String) -> void:
	var lu = JSON.parse_string(brut)
	if typeof(lu) != TYPE_DICTIONARY:
		return
	if lu.has("etat"):
		etat = lu["etat"]
	elif lu.get("type", "") == "etat":
		etat = lu
	_placer()


func _placer() -> void:
	## Un bloc par groupe, les etudiants ranges en grille a l'interieur.
	var par_groupe := {}
	for a in etat.get("agents", []):
		var g: String = a.get("groupe", "?")
		if not par_groupe.has(g):
			par_groupe[g] = []
		par_groupe[g].append(a)
	var noms := par_groupe.keys()
	noms.sort()
	zones.clear()
	positions.clear()
	var colonnes := 3
	var largeur := 282.0
	var hauteur := 196.0
	for i in noms.size():
		var col := i % colonnes
		var lig := i / colonnes
		var zone := Rect2(28 + col * (largeur + 10), 96 + lig * (hauteur + 12),
			largeur, hauteur)
		zones[noms[i]] = zone
		var liste: Array = par_groupe[noms[i]]
		for j in liste.size():
			var cx: float = zone.position.x + 40 + (j % 5) * 50
			var cy: float = zone.position.y + 64 + float(j / 5) * 56
			positions[liste[j]["id"]] = Vector2(cx, cy)


func _unhandled_input(event: InputEvent) -> void:
	if not (event is InputEventMouseButton and event.pressed
			and event.button_index == MOUSE_BUTTON_LEFT):
		return
	var p: Vector2 = event.position
	for b in boutons:
		if (b["rect"] as Rect2).has_point(p):
			_injecter(b["nature"])
			return
	for id in positions:
		if (positions[id] as Vector2).distance_to(p) <= RAYON + 6:
			selection = id
			return
	selection = ""


func _injecter(nature: String) -> void:
	## Demande au pont de bousculer le monde. La scene ne decide de rien :
	## elle demande, le pont publie, la simulation applique.
	if ws.get_ready_state() != WebSocketPeer.STATE_OPEN:
		return
	ws.send_text(JSON.stringify({"type": "injection", "nature": nature, "details": {}}))


# ------------------------------------------------------------------ dessin


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, get_viewport_rect().size), FOND)
	_entete()
	_groupes()
	_courbe()
	_repartition()
	_boutons()
	_panneau()


func _txt(pos: Vector2, texte: String, taille := 14, couleur := ENCRE) -> void:
	draw_string(police, pos, texte, HORIZONTAL_ALIGNMENT_LEFT, -1, taille, couleur)


func _entete() -> void:
	var ind: Dictionary = etat.get("indicateurs", {})
	_txt(Vector2(28, 40), "Tessaline", 26)
	var quand: String = ind.get("t_sim_lisible", "")
	if quand == "":
		quand = "en attente"
	_txt(Vector2(28, 66), "temps simule %s" % quand, 14, DOUX)

	if not ind.is_empty():
		var taux: float = ind.get("taux_adoption", 0.0)
		var part: float = ind.get("part_sens_dominant", 0.0)
		var dom: String = ind.get("sens_dominant", "")
		_txt(Vector2(330, 44), "adoption %d%%" % int(round(taux * 100)), 18)
		_txt(Vector2(500, 44), "sens dominant : %s a %d%%"
			% [LIBELLES.get(dom, dom), int(round(part * 100))], 18,
			COULEURS.get(dom, ENCRE))
		_txt(Vector2(330, 66), "%d evenements recus" % int(ind.get("evenements_vus", 0)),
			12, DOUX)

	var etiquette := "pont connecte" if connecte else "pont absent, nouvel essai..."
	var couleur := Color("#2a9d8f") if connecte else Color("#c8553d")
	_txt(Vector2(PANNEAU_X, 40), etiquette, 12, couleur)


func _groupes() -> void:
	for nom in zones:
		var zone: Rect2 = zones[nom]
		draw_rect(zone, Color(1, 1, 1, 0.75))
		draw_rect(zone, TRAIT, false, 1.0)
		_txt(zone.position + Vector2(12, 24), (nom as String).replace("_", " "), 14, DOUX)
	for a in etat.get("agents", []):
		var id: String = a["id"]
		if not positions.has(id):
			continue
		var centre: Vector2 = positions[id]
		var cat: String = a.get("categorie", "aucun_sens")
		var couleur: Color = COULEURS.get(cat, DOUX)
		if a.get("porte", false):
			draw_circle(centre, RAYON, couleur)
			# Le ruban : un arc autour du poignet, de la couleur du sens.
			draw_arc(centre, RAYON + 5, 0.6, 2.54, 24, couleur.darkened(0.25), 3.0)
		else:
			draw_circle(centre, RAYON, Color(1, 1, 1, 1))
			draw_arc(centre, RAYON, 0, TAU, 28, couleur, 2.0)
		if not a.get("valide", true):
			# Agent dont la derniere reponse etait inexploitable (exigence A4).
			draw_arc(centre, RAYON + 9, 0, TAU, 28, Color("#c8553d"), 1.5)
		if id == selection:
			draw_arc(centre, RAYON + 13, 0, TAU, 32, ENCRE, 2.0)
		var initiale: String = (a.get("nom", "?") as String).substr(0, 1)
		_txt(centre + Vector2(-5, 5), initiale, 14,
			ENCRE if not a.get("porte", false) else Color(1, 1, 1))


func _courbe() -> void:
	## La courbe de vie de la tendance, en cours de construction.
	## Chaque point prend la couleur du sens dominant a ce moment-la : on lit
	## donc d'un coup d'oeil QUAND le ruban a change de signification.
	var x := 28.0
	var y := 524.0
	var l := 854.0
	var h := 150.0
	draw_rect(Rect2(x, y, l, h), Color(1, 1, 1, 0.75))
	draw_rect(Rect2(x, y, l, h), TRAIT, false, 1.0)
	_txt(Vector2(x + 12, y + 20), "vie de la tendance", 12, DOUX)

	var hist: Array = etat.get("historique", [])
	if hist.size() < 2:
		_txt(Vector2(x + 12, y + 80), "en attente de donnees...", 12, DOUX)
		return

	var bas := y + h - 22.0
	var haut := y + 32.0
	# Reperes 0, 50 et 100 pour cent.
	for part in [0.0, 0.5, 1.0]:
		var yy: float = bas - part * (bas - haut)
		draw_line(Vector2(x + 44, yy), Vector2(x + l - 14, yy), TRAIT, 1.0)
		_txt(Vector2(x + 12, yy + 4), "%d%%" % int(part * 100), 10, DOUX)

	var pas: float = (l - 62.0) / float(max(1, hist.size() - 1))
	var points := PackedVector2Array()
	for i in hist.size():
		var t: float = float(hist[i].get("taux_adoption", 0.0))
		points.append(Vector2(x + 46 + i * pas, bas - t * (bas - haut)))
	draw_polyline(points, DOUX, 2.0)
	for i in hist.size():
		var dom: String = hist[i].get("sens_dominant", "aucun_sens")
		draw_circle(points[i], 4.0, COULEURS.get(dom, DOUX))
	var dernier: Dictionary = hist[hist.size() - 1]
	_txt(Vector2(x + l - 150, y + 20), "%s  %d%%"
		% [dernier.get("t_sim_lisible", ""),
		int(round(float(dernier.get("taux_adoption", 0.0)) * 100))], 12, DOUX)


func _repartition() -> void:
	## Ce que le ruban veut dire, maintenant, pour tout le campus.
	## Une barre empilee : si une couleur occupe toute la largeur, le campus
	## s'accorde sur un sens unique, et c'est cela que mesure l'indicateur.
	var ind: Dictionary = etat.get("indicateurs", {})
	var repartition: Dictionary = ind.get("repartition_sens", {})
	if repartition.is_empty():
		return
	var total := 0
	for cle in repartition:
		total += int(repartition[cle])
	if total == 0:
		return

	var x := 28.0
	var y := 690.0
	var l := 854.0
	_txt(Vector2(x, y - 6), "ce que le ruban veut dire, maintenant", 12, DOUX)
	var curseur := x
	var ordre := ["cercle_creatif", "tendance", "suivre_la_foule", "ironie",
		"ringard", "aucun_sens"]
	for cle in ordre:
		var n := int(repartition.get(cle, 0))
		if n == 0:
			continue
		var large: float = l * float(n) / float(total)
		draw_rect(Rect2(curseur, y, large, 14), COULEURS.get(cle, DOUX))
		if large > 74:
			_txt(Vector2(curseur + 5, y + 11), "%s %d" % [LIBELLES.get(cle, cle), n],
				10, Color(1, 1, 1, 0.95))
		curseur += large


func _boutons() -> void:
	_txt(Vector2(28, 716), "bousculer le monde", 12, DOUX)
	for b in boutons:
		var r: Rect2 = b["rect"]
		draw_rect(r, Color(1, 1, 1, 0.9))
		draw_rect(r, TRAIT, false, 1.0)
		_txt(r.position + Vector2(14, 24), b["titre"], 13, ENCRE)


func _panneau() -> void:
	var x := PANNEAU_X
	var y := 96.0
	var l := 372.0
	draw_rect(Rect2(x, y, l, 596), Color(1, 1, 1, 0.85))
	draw_rect(Rect2(x, y, l, 596), TRAIT, false, 1.0)
	y += 30
	_txt(Vector2(x + 16, y), "Etudiant inspecte", 16)
	y += 26

	var agent := {}
	for a in etat.get("agents", []):
		if a["id"] == selection:
			agent = a
	if agent.is_empty():
		_txt(Vector2(x + 16, y), "Cliquez sur un etudiant.", 13, DOUX)
	else:
		_txt(Vector2(x + 16, y), "%s, %s" % [agent.get("nom", ""),
			(agent.get("profil", "") as String).replace("_", " ")], 15)
		y += 22
		_txt(Vector2(x + 16, y), "groupe %s, moteur %s"
			% [agent.get("groupe", ""), agent.get("moteur", "")], 12, DOUX)
		y += 26
		var cat: String = agent.get("categorie", "aucun_sens")
		_txt(Vector2(x + 16, y), "sens : %s" % LIBELLES.get(cat, cat), 14,
			COULEURS.get(cat, ENCRE))
		y += 22
		y = _bloc(x + 16, y, l - 32, agent.get("sens", ""))
		y += 8
		_txt(Vector2(x + 16, y), "derniere decision", 12, DOUX)
		y += 18
		y = _bloc(x + 16, y, l - 32, agent.get("raison", ""))
		y += 10
		_txt(Vector2(x + 16, y), "memoire", 12, DOUX)
		y += 18
		for m in agent.get("memoire", []):
			y = _bloc(x + 16, y, l - 32, "%s  %s" % [m.get("t_sim_lisible", ""),
				m.get("fait", "")])
			y += 2

	# Le fil du reseau interne, en bas du panneau.
	y = 500.0
	_txt(Vector2(x + 16, y), "reseau interne", 12, DOUX)
	y += 18
	var fil: Array = etat.get("fil", [])
	for i in range(max(0, fil.size() - 6), fil.size()):
		var m: Dictionary = fil[i]
		y = _bloc(x + 16, y, l - 32, "%s : %s" % [m.get("auteur", ""), m.get("texte", "")])
		y += 2


func _bloc(x: float, y: float, largeur: float, texte: String) -> float:
	## Texte coupe en lignes, a la louche : 1 caractere vaut environ 7 pixels.
	if texte == "":
		return y
	var par_ligne := int(largeur / 7.0)
	var reste := texte
	var lignes := 0
	while reste.length() > 0 and lignes < 4:
		var bout: String = reste.substr(0, par_ligne)
		if reste.length() > par_ligne:
			var coupe := bout.rfind(" ")
			if coupe > par_ligne / 2:
				bout = bout.substr(0, coupe)
		_txt(Vector2(x, y), bout, 12, ENCRE)
		reste = reste.substr(bout.length()).strip_edges()
		y += 16
		lignes += 1
	return y
