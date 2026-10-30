extends Node2D
## Campus de Tessaline en direct.
## Les données arrivent de pont.py par WebSocket. Rien n'est calculé ici :
## la scène AFFICHE, elle ne simule pas.
##
## Clic sur un étudiant : sa mémoire et la justification de sa dernière
## décision (exigence D2). En v2, la justification est le détail du score
## (chaque terme, puis S) et les sources qui ont fait changer ses croyances.
## Sans sélection, le panneau montre ce que le ruban veut dire, groupe par
## groupe et jour par jour (exigence B1), puis le fil du réseau interne.
## Boutons en bas : injection d'un événement dans le monde en cours (D3).
##
## Ce qui bouge (exigence D1) : un message privé file le long du lien qui
## relie deux étudiants, une publication publique part en onde, un étudiant
## qui change de choix ou de sens s'éclaire un instant, et un bandeau
## s'allume quand une contre-tendance apparaît (le pont la repère).
##
## Le campus est un plan : chaque groupe est un bâtiment, et les ponts du
## réseau tracent les chemins entre bâtiments. Le modèle n'a pas d'autre
## espace (en v2, le "lieu" où l'on croise des gens est le groupe) : le plan
## ne montre aucun déplacement, il montre QUI A VU QUI ce jour-là, d'après
## perception.v2. Ces regards sont la seule rencontre que le modèle connaît.
## Le relief des bâtiments est un simple effet de dessin, en 2D.
##
## Vue 3D (campus3d.gd, demandée par l'encadrant) : elle prend la place du plan,
## avec les mêmes données et les mêmes règles de lecture ; le panneau, le
## tableau B1, la courbe et les boutons restent en 2D. V bascule 3D / plan 2D.
##
## Clavier : L passe des regards du jour au réseau, Échap désélectionne,
## G bascule le rendu 3D entre haute qualité et léger.
## En rejeu : espace met en pause, flèches gauche et droite changent de jour,
## un clic sur la courbe ou sur le tableau des groupes va à ce jour.

const URL := "ws://localhost:8765"
const RAYON_MAX := 20.0
const DUREE_VOL := 0.9
const DUREE_ONDE := 1.1
const DUREE_ECLAT := 1.2
const DUREE_ALERTE := 5.0
const JOUR := 1440

# Une couleur par sens possible du ruban. C'est la lecture principale de
# la scène : la couleur dit ce que le ruban VEUT DIRE pour cet étudiant.
var COULEURS := {
	"cercle_creatif": Color("#7b5cd6"),
	"tendance": Color("#2a9d8f"),
	"suivre_la_foule": Color("#e9a23b"),
	"ringard": Color("#c8553d"),
	"ironie": Color("#3d7cc8"),
	"aucun_sens": Color("#9a97a6"),
}
const LIBELLES := {
	"cercle_creatif": "cercle créatif", "tendance": "tendance",
	"suivre_la_foule": "suit la foule", "ringard": "ringard",
	"ironie": "ironie", "aucun_sens": "aucun sens",
}
const ORDRE_SENS := ["cercle_creatif", "tendance", "suivre_la_foule", "ironie",
	"ringard", "aucun_sens"]
const INJECTIONS := {
	"relais_massif": "relais", "tendance_rivale": "rivale",
	"message": "rumeur", "cloisonnement": "cloison",
}
# Les identifiants de la simulation restent sans accents (contrat
# d'événements) ; seul l'affichage les accentue.
const GROUPES := {
	"atelier_design": "atelier de design", "cafeteria": "cafétéria",
	"asso_sportive": "asso sportive", "residence_a": "résidence A",
	"club_humour": "club humour", "residence_b": "résidence B",
}
const PROFILS := {
	"pionnier": "pionnier", "figure_populaire": "figure populaire",
	"suiveur": "suiveur", "refractaire": "réfractaire", "ironique": "ironique",
}
const MOTS := [
	["atelier design", "atelier de design"], ["cafeteria", "cafétéria"],
	["residence", "résidence"], ["creatif", "créatif"], ["depasse", "dépassé"],
	["ca ne veut", "ça ne veut"], ["refractaire", "réfractaire"],
]
const PRENOMS := ["Ines:Inès", "Lea:Léa", "Theo:Théo", "Ismail:Ismaïl",
	"Said:Saïd", "Chaima:Chaïma"]

var FOND := Color("#f7f6fa")
var ENCRE := Color("#24212e")
var DOUX := Color("#64607a")
var TRAIT := Color("#dcd8e6")
var ALERTE := Color("#c8553d")
var VERT := Color("#2a9d8f")
var SOL := Color("#e9ece2")
var CHEMIN := Color("#d6d0bd")
const PANNEAU_X := 920.0
const ZONE_GROUPES := Rect2(28, 118, 842, 382)
const PROFONDEUR := Vector2(12, -10)   # relief des bâtiments
# Place de chaque bâtiment sur le plan, en case (colonne, ligne). Un groupe
# absent de cette table prend la première case libre.
const PLAN := {
	"atelier_design": Vector2i(0, 0), "cafeteria": Vector2i(1, 0),
	"asso_sportive": Vector2i(2, 0), "residence_a": Vector2i(0, 1),
	"club_humour": Vector2i(1, 1), "residence_b": Vector2i(2, 1),
}
const ECART := Vector2(52, 60)
const COURBE := Rect2(28, 516, 854, 150)
const RECT_3D := Rect2(18, 100, 874, 408)
const BOUTON_VUE := Rect2(770, 50, 112, 24)

var ws := WebSocketPeer.new()
var connecte := false
var delai_reco := 0.0
var etat := {}
var positions := {}
var rayons := {}
var etiquettes := {}   # id -> lettres uniques dans le rond
var noms_sous := false # place pour écrire le prénom sous chaque rond
var zones := {}
var cases := {}
var ordre_groupes := []
var par_nom := {}
var voisins := {}
var selection := ""
var survol := ""
var voir_reseau := false   # faux : regards du jour ; vrai : réseau
var regards_age := 0.0
var regards_t = null
var police: Font
var police_forte: Font
var regles_prenoms := []
var boutons := []
var bouton_lecture := Rect2()
var vue3d               # campus3d.gd
var en_3d := true
var tableau := {}      # géométrie du tableau B1, pour les clics

# Animations, toutes en secondes restantes.
var vols := []      # {de, vers, couleur, reste}
var ondes := []     # {centre, couleur, reste}
var eclats := {}    # id -> reste
var bandeau := {"texte": "", "couleur": Color.BLACK, "reste": 0.0}
var contre_vues := 0
var alerte := 0.0


func _ready() -> void:
	police = _charger_police("res://polices/NotoSans-Regular.ttf")
	police_forte = _charger_police("res://polices/NotoSans-SemiBold.ttf")
	for paire in PRENOMS:
		var p: PackedStringArray = (paire as String).split(":")
		var re := RegEx.new()
		re.compile("\\b%s\\b" % p[0])
		regles_prenoms.append([re, p[1]])
	_poser_boutons()
	vue3d = preload("res://campus3d.gd").new()
	vue3d.position = RECT_3D.position
	vue3d.size = RECT_3D.size
	vue3d.couleurs = COULEURS
	vue3d.plan = PLAN
	vue3d.police = police_forte
	vue3d.groupes_lisibles = GROUPES
	vue3d.lisible = _prenom
	add_child(vue3d)
	vue3d.agent_clique.connect(_choisir)
	ws.connect_to_url(URL)


func _choisir(id: String) -> void:
	selection = id


func _charger_police(chemin: String) -> Font:
	## Police complète (accents compris), lue directement depuis le fichier :
	## pas besoin de l'importer dans l'éditeur. Repli sur la police par défaut.
	if FileAccess.file_exists(chemin):
		var f := FontFile.new()
		if f.load_dynamic_font(chemin) == OK:
			return f
	return ThemeDB.fallback_font


func _poser_boutons() -> void:
	var noms := [
		{"titre": "Relais massif", "nature": "relais_massif"},
		{"titre": "Tendance rivale", "nature": "tendance_rivale"},
		{"titre": "Rumeur", "nature": "message"},
		{"titre": "Cloisonner", "nature": "cloisonnement"},
	]
	var x := 28.0
	for n in noms:
		boutons.append({"titre": n["titre"], "nature": n["nature"],
			"rect": Rect2(x, 734, 200, 32)})
		x += 214.0


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
	_vieillir(delta)
	vue3d.selection = selection
	vue3d.voir_reseau = voir_reseau
	survol = vue3d.survol if en_3d else _agent_sous(get_global_mouse_position())
	queue_redraw()


func _vieillir(delta: float) -> void:
	for v in vols:
		v["reste"] -= delta
	vols = vols.filter(func(v): return v["reste"] > 0.0)
	for o in ondes:
		o["reste"] -= delta
	ondes = ondes.filter(func(o): return o["reste"] > 0.0)
	for id in eclats.keys():
		eclats[id] -= delta
		if eclats[id] <= 0.0:
			eclats.erase(id)
	bandeau["reste"] = maxf(0.0, float(bandeau["reste"]) - delta)
	alerte = maxf(0.0, alerte - delta)
	regards_age += delta


# ------------------------------------------------------------ réception


func _recevoir(brut: String) -> void:
	var lu = JSON.parse_string(brut)
	if typeof(lu) != TYPE_DICTIONARY:
		return
	if lu.get("type", "") == "accuse":
		_annoncer(lu)
		return
	var avant := {}
	for a in etat.get("agents", []):
		avant[a["id"]] = [a.get("porte", false), a.get("categorie", "")]
	var run_avant: String = str(etat.get("run", ""))
	var jour_avant := _jour()
	if lu.has("etat"):
		etat = lu["etat"]
	elif lu.get("type", "") == "etat":
		etat = lu
	var saut: bool = not lu.has("evenement")   # instantané seul : connexion ou saut de rejeu
	if str(etat.get("run", "")) != run_avant:
		selection = ""
		saut = true
	if saut or absi(_jour() - jour_avant) > 1:
		avant.clear()
		vols.clear()
		ondes.clear()
		eclats.clear()
		vue3d.vider_animations()
	_placer()
	vue3d.mettre_a_jour(etat, voisins)
	# Un nouveau jour de regards apparaît en fondu.
	if str(etat.get("regards_t")) != str(regards_t):
		regards_t = etat.get("regards_t")
		regards_age = 0.0
	# Un étudiant qui change de choix ou de sens s'éclaire un instant.
	for a in etat.get("agents", []):
		if avant.has(a["id"]):
			var p: Array = avant[a["id"]]
			if p[0] != a.get("porte", false) or p[1] != a.get("categorie", ""):
				eclats[a["id"]] = DUREE_ECLAT
				vue3d.eclater(a["id"])
	# Une contre-tendance nouvelle allume le bandeau ; après un saut, on
	# reprend le compte sans rien allumer.
	var n: int = etat.get("contre_tendances", []).size()
	if n > contre_vues and not saut:
		alerte = DUREE_ALERTE
	contre_vues = n
	if lu.has("evenement"):
		_animer(lu["evenement"])


func _animer(evt: Dictionary) -> void:
	var schema: String = evt.get("schema", "")
	if schema == "publication.v1" or schema == "publication.v2" or schema == "replique.v1":
		var de: String = evt.get("agent", "")
		if not positions.has(de):
			return
		var couleur: Color = COULEURS.get(str(evt.get("categorie", "")), DOUX)
		var vers := _id_de(str(evt.get("destinataire", "")))
		var prive: bool = schema == "replique.v1" or evt.get("portee", "campus") == "personne"
		if prive and vers != "":
			vols.append({"de": de, "vers": vers, "couleur": couleur, "reste": DUREE_VOL})
			vue3d.animer_message(de, vers, couleur)
		else:
			ondes.append({"centre": positions[de], "couleur": couleur, "reste": DUREE_ONDE})
			vue3d.animer_message(de, "", couleur)
	elif schema == "injection.v1":
		bandeau = {"texte": "injection : %s" % str(evt.get("nature", "")).replace("_", " "),
			"couleur": ENCRE, "reste": 3.0}


func _annoncer(accuse: Dictionary) -> void:
	var nature: String = str(accuse.get("nature", "")).replace("_", " ")
	var ok: bool = accuse.get("ok", false)
	bandeau = {"texte": "%s : %s" % [nature, accuse.get("texte", "")],
		"couleur": VERT if ok else ALERTE, "reste": 4.0}


func _id_de(cle: String) -> String:
	## v2 nomme le destinataire par son id, v1 par son nom.
	if positions.has(cle):
		return cle
	return par_nom.get(cle.to_lower(), "")


func _jour() -> int:
	## Jours simulés écoulés. Le relevé de t = 25 x 1440 s'écrit "J26 00:00",
	## mais c'est la FIN du jour 25 : le run de 25 jours ne dure pas 26 jours.
	return int(etat.get("indicateurs", {}).get("t_sim", 0)) / JOUR


func _jours() -> int:
	var r: Dictionary = etat.get("rejeu", {})
	if r.has("jours"):
		return int(r["jours"])
	if etat.get("jours") != null:
		return int(etat["jours"])
	return maxi(1, etat.get("historique", []).size() - 1)


func _placer() -> void:
	## Un bâtiment par groupe, les étudiants rangés en grille à l'intérieur.
	## La grille et la taille des ronds suivent l'effectif : 20, 50 ou 100.
	var par_groupe := {}
	par_nom.clear()
	for a in etat.get("agents", []):
		var g: String = a.get("groupe", "?")
		if not par_groupe.has(g):
			par_groupe[g] = []
		par_groupe[g].append(a)
		par_nom[str(a.get("nom", "")).to_lower()] = a["id"]
	var noms := par_groupe.keys()
	noms.sort()
	zones.clear()
	cases.clear()
	positions.clear()
	rayons.clear()
	var prises := {}
	for nom in noms:
		if PLAN.has(nom):
			cases[nom] = PLAN[nom]
			prises[PLAN[nom]] = true
	for nom in noms:
		if not cases.has(nom):
			var k := 0
			while prises.has(Vector2i(k % 3, k / 3)):
				k += 1
			cases[nom] = Vector2i(k % 3, k / 3)
			prises[cases[nom]] = true
	ordre_groupes = noms.duplicate()
	ordre_groupes.sort_custom(_avant_sur_plan)
	var colonnes := 3
	var lignes := 1
	for nom in cases:
		lignes = maxi(lignes, (cases[nom] as Vector2i).y + 1)
	var largeur := (ZONE_GROUPES.size.x - ECART.x * (colonnes - 1)) / colonnes
	var hauteur := (ZONE_GROUPES.size.y - ECART.y * (lignes - 1)) / lignes
	noms_sous = true
	for nom in noms:
		var cell: Vector2i = cases[nom]
		var zone := Rect2(ZONE_GROUPES.position.x + cell.x * (largeur + ECART.x),
			ZONE_GROUPES.position.y + cell.y * (hauteur + ECART.y), largeur, hauteur)
		zones[nom] = zone
		var liste: Array = par_groupe[nom]
		var interieur := Rect2(zone.position + Vector2(12, 34), zone.size - Vector2(24, 40))
		var n := liste.size()
		var cols := clampi(ceili(sqrt(n * interieur.size.x / interieur.size.y)), 1, n)
		var rangs := ceili(float(n) / cols)
		var pas := Vector2(interieur.size.x / cols, interieur.size.y / rangs)
		if pas.x < 48.0 or pas.y < 48.0:
			noms_sous = false
		var r := clampf(minf(pas.x, pas.y) * 0.3, 6.0, RAYON_MAX)
		for j in n:
			var c := Vector2(j % cols + 0.5, j / cols + 0.5)
			# Un peu plus haut que le centre de la case : le prénom va dessous.
			positions[liste[j]["id"]] = interieur.position + c * pas - Vector2(0, pas.y * 0.1)
			rayons[liste[j]["id"]] = r
	_etiqueter()
	voisins.clear()
	for l in etat.get("liens", []):
		for paire in [[l["a"], l["b"]], [l["b"], l["a"]]]:
			if not voisins.has(paire[0]):
				voisins[paire[0]] = {}
			voisins[paire[0]][paire[1]] = l["type"]


func _avant_sur_plan(a, b) -> bool:
	## Ordre de lecture du plan : ligne par ligne, de gauche à droite.
	var ca: Vector2i = cases[a]
	var cb: Vector2i = cases[b]
	return ca.y * 10 + ca.x < cb.y * 10 + cb.x


func _etiqueter() -> void:
	## Les lettres dans chaque rond : le plus court début de prénom qui ne
	## désigne qu'un seul étudiant ("Ad" et "Ay", pas deux "A").
	etiquettes.clear()
	var prenoms := {}
	for a in etat.get("agents", []):
		prenoms[a["id"]] = _prenom(str(a.get("nom", "?")))
	for id in prenoms:
		var p: String = prenoms[id]
		var longueur := 1
		while longueur < 3:
			var unique := true
			for autre in prenoms:
				if autre != id and (prenoms[autre] as String).begins_with(p.substr(0, longueur)):
					unique = false
					break
			if unique:
				break
			longueur += 1
		var lettres := p.substr(0, longueur)
		var morceaux := p.split(" ")   # "Ines 2" à 100 agents
		if morceaux.size() > 1:
			lettres = p.substr(0, 1) + morceaux[1]
		etiquettes[id] = lettres


func _agent_sous(p: Vector2) -> String:
	for id in positions:
		if (positions[id] as Vector2).distance_to(p) <= float(rayons[id]) + 6:
			return id
	return ""


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_L:
			voir_reseau = not voir_reseau
		elif event.keycode == KEY_ESCAPE:
			selection = ""
		elif event.keycode == KEY_V:
			_basculer_vue()
		elif event.keycode == KEY_G:
			vue3d.regler_qualite(not vue3d.haute_qualite)
			bandeau = {"texte": "rendu 3D " + ("haute qualité" if vue3d.haute_qualite else "léger"),
				"couleur": ENCRE, "reste": 2.0}
		elif event.keycode == KEY_SPACE:
			_basculer_lecture()
		elif event.keycode == KEY_LEFT:
			_aller_a(_jour() - 1)
		elif event.keycode == KEY_RIGHT:
			_aller_a(_jour() + 1)
		return
	if not (event is InputEventMouseButton and event.pressed
			and event.button_index == MOUSE_BUTTON_LEFT):
		return
	var p: Vector2 = event.position
	if BOUTON_VUE.has_point(p):
		_basculer_vue()
		return
	for b in boutons:
		if (b["rect"] as Rect2).has_point(p):
			_injecter(b["nature"])
			return
	if etat.has("rejeu"):
		if bouton_lecture.has_point(p):
			_basculer_lecture()
			return
		var trace := _trace_courbe()
		if trace.grow(6).has_point(p):
			_aller_a(roundi((p.x - trace.position.x) / trace.size.x * _jours()))
			return
		if not tableau.is_empty() and (tableau["rect"] as Rect2).has_point(p):
			var r: Rect2 = tableau["rect"]
			_aller_a(int((p.x - r.position.x) / float(tableau["colonne"])))
			return
	# En 3D, les clics sur le campus passent par campus3d.gd (signal agent_clique).
	selection = "" if en_3d else _agent_sous(p)


func _basculer_vue() -> void:
	en_3d = not en_3d
	vue3d.visible = en_3d


func _envoyer(message: Dictionary) -> bool:
	if ws.get_ready_state() != WebSocketPeer.STATE_OPEN:
		bandeau = {"texte": "pont absent", "couleur": ALERTE, "reste": 3.0}
		return false
	ws.send_text(JSON.stringify(message))
	return true


func _aller_a(jour: int) -> void:
	## En rejeu seulement : le pont reconstruit l'état à la fin de ce jour.
	if etat.has("rejeu"):
		_envoyer({"type": "rejeu", "action": "aller_a", "jour": clampi(jour, 0, _jours())})


func _basculer_lecture() -> void:
	if etat.has("rejeu"):
		var en_pause: bool = etat["rejeu"].get("pause", false)
		_envoyer({"type": "rejeu", "action": "lecture" if en_pause else "pause"})


func _injections_possibles() -> bool:
	## Le modèle v2 ne lit pas encore les commandes (étape 7 de la migration).
	return connecte and etat.get("modele_social", "v1") != "v2" and not etat.has("rejeu")


func _injecter(nature: String) -> void:
	## Demande au pont de bousculer le monde. La scène ne décide de rien :
	## elle demande, le pont publie, la simulation applique. Le pont répond
	## par un accusé, affiché dans le bandeau.
	_envoyer({"type": "injection", "nature": nature, "details": {}})


# ------------------------------------------------------------------ texte


func _lisible(texte: String) -> String:
	## Accents des textes venus de la simulation, pour l'affichage seulement.
	for m in MOTS:
		texte = texte.replace(m[0], m[1])
	for r in regles_prenoms:
		texte = (r[0] as RegEx).sub(texte, r[1], true)
	return texte


func _prenom(nom: String) -> String:
	return _lisible(nom)


func _groupe(g: String) -> String:
	return GROUPES.get(g, g.replace("_", " "))


func _txt(pos: Vector2, texte: String, taille := 14, couleur := ENCRE, forte := false) -> void:
	draw_string(police_forte if forte else police, pos, texte, HORIZONTAL_ALIGNMENT_LEFT,
		-1, taille, couleur)


func _largeur(texte: String, taille: int, forte := false) -> float:
	var f: Font = police_forte if forte else police
	return f.get_string_size(texte, HORIZONTAL_ALIGNMENT_LEFT, -1, taille).x


func _pastille(centre: Vector2, texte: String, taille := 10, couleur := DOUX) -> Rect2:
	## Une étiquette sur fond clair, lisible au-dessus des chemins et des toits.
	var l := _largeur(texte, taille) + 10.0
	var r := Rect2(centre - Vector2(l / 2.0, taille * 0.8), Vector2(l, taille * 1.6))
	draw_rect(r, Color(FOND, 0.94))
	draw_rect(r, Color(couleur, 0.5), false, 1.0)
	_txt(Vector2(r.position.x + 5, centre.y + taille * 0.36), texte, taille, couleur)
	return r


# ------------------------------------------------------------------ dessin


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, get_viewport_rect().size), FOND)
	_entete()
	_legende()
	_bouton_vue()
	if not en_3d:
		_groupes()
	_courbe()
	_repartition()
	_boutons()
	_panneau()
	if not en_3d:
		_infobulle()


func _bouton_vue() -> void:
	var dedans := BOUTON_VUE.has_point(get_global_mouse_position())
	draw_rect(BOUTON_VUE, Color(1, 1, 1, 1.0 if dedans else 0.9))
	draw_rect(BOUTON_VUE, ENCRE if dedans else TRAIT.darkened(0.15), false, 1.0)
	var texte := "plan 2D (V)" if en_3d else "vue 3D (V)"
	_txt(BOUTON_VUE.position + Vector2((BOUTON_VUE.size.x - _largeur(texte, 12)) / 2.0, 17),
		texte, 12, ENCRE)


func _entete() -> void:
	var ind: Dictionary = etat.get("indicateurs", {})
	_txt(Vector2(28, 42), "Tessaline", 26, ENCRE, true)
	var quand := "en attente"
	if not ind.is_empty():
		var t := int(ind.get("t_sim", 0))
		if t == 0:
			quand = "début du run"
		elif t % JOUR == 0:
			quand = "fin du jour %d sur %d" % [t / JOUR, _jours()]
		else:
			quand = "jour %d sur %d, %s" % [t / JOUR + 1, _jours(),
				str(ind.get("t_sim_lisible", "")).substr(4)]
	_txt(Vector2(28, 66), quand, 14, DOUX)

	if not ind.is_empty():
		var taux: float = ind.get("taux_adoption", 0.0)
		var part: float = ind.get("part_sens_dominant", 0.0)
		var dom: String = ind.get("sens_dominant", "")
		_txt(Vector2(250, 44), "adoption %d %%" % int(round(taux * 100)), 18, ENCRE, true)
		_txt(Vector2(410, 44), "sens dominant : %s à %d %%"
			% [LIBELLES.get(dom, dom), int(round(part * 100))], 18,
			COULEURS.get(dom, ENCRE), true)
		var details: String = "modèle %s" % str(etat.get("modele_social", "v1"))
		if etat.get("cloisonne", false):
			details += ", cloisonné"
		details += "   %d événements reçus" % int(ind.get("evenements_vus", 0))
		_txt(Vector2(250, 66), details, 12, DOUX)

	var etiquette := "pont connecté" if connecte else "pont absent, nouvel essai..."
	if connecte and etat.has("rejeu"):
		etiquette += ", rejeu"
	_txt(Vector2(PANNEAU_X, 40), etiquette, 12, VERT if connecte else ALERTE)
	var run: String = str(etat.get("run", ""))
	if run != "" and run != "<null>":
		_txt(Vector2(PANNEAU_X, 60), run, 11, DOUX)
	if float(bandeau["reste"]) > 0.0:
		var c: Color = bandeau["couleur"]
		c.a = clampf(float(bandeau["reste"]), 0.0, 1.0)
		_txt(Vector2(PANNEAU_X, 80), bandeau["texte"], 12, c)


func _legende() -> void:
	## La clé de lecture, toujours visible : un observateur qui ne connaît pas
	## le code doit pouvoir lire la scène seul (exigence D1).
	var x := 28.0
	var y := 92.0
	for cle in ORDRE_SENS:
		draw_circle(Vector2(x + 5, y - 4), 5.0, COULEURS[cle])
		_txt(Vector2(x + 14, y), LIBELLES[cle], 11, DOUX)
		x += 22.0 + _largeur(LIBELLES[cle], 11)
	x += 10.0
	var porte := "corps franc + anneau : porte" if en_3d else "plein : porte"
	var porte_pas := "pâle : ne porte pas" if en_3d else "vide : ne porte pas"
	draw_circle(Vector2(x + 6, y - 4), 6.0, DOUX)
	_txt(Vector2(x + 16, y), porte, 11, DOUX)
	x += 30.0 + _largeur(porte, 11)
	if en_3d:
		draw_circle(Vector2(x + 6, y - 4), 6.0, DOUX.lerp(Color.WHITE, 0.72))
	else:
		draw_arc(Vector2(x + 6, y - 4), 6.0, 0, TAU, 16, DOUX, 1.5)
	_txt(Vector2(x + 16, y), porte_pas, 11, DOUX)
	x += 16.0 + _largeur(porte_pas, 11)
	if not etat.get("liens", []).is_empty():
		var mode := "traits : réseau (L)" if voir_reseau else "traits : regards du jour (L)"
		var debut := PANNEAU_X - 14.0 - _largeur(mode, 11)
		if debut > x + 12.0:
			_txt(Vector2(debut, y), mode, 11, DOUX)


# ------------------------------------------------------------------ plan


func _ponts_par_paire() -> Dictionary:
	## "groupe_a|groupe_b" -> nombre de ponts du réseau entre les deux groupes.
	var groupe := {}
	for a in etat.get("agents", []):
		groupe[a["id"]] = a.get("groupe", "?")
	var ponts := {}
	for l in etat.get("liens", []):
		if l["type"] != "faible" or not (groupe.has(l["a"]) and groupe.has(l["b"])):
			continue
		var paire := [groupe[l["a"]], groupe[l["b"]]]
		paire.sort()
		var cle := "%s|%s" % paire
		ponts[cle] = int(ponts.get(cle, 0)) + 1
	return ponts


func _voisins_sur_plan(g1: String, g2: String) -> bool:
	var d: Vector2i = (cases[g1] as Vector2i) - (cases[g2] as Vector2i)
	return absi(d.x) + absi(d.y) == 1


func _arc(a: Vector2, b: Vector2) -> PackedVector2Array:
	## Un arc entre deux bâtiments éloignés, bombé vers l'extérieur du plan.
	var milieu := a.lerp(b, 0.5)
	var normale := Vector2(-(b - a).y, (b - a).x).normalized()
	var dehors := milieu - ZONE_GROUPES.get_center()
	if normale.dot(dehors) < 0.0 or (absf(normale.dot(dehors)) < 1.0 and normale.y > 0.0):
		normale = -normale
	var controle := milieu + normale * minf(a.distance_to(b) * 0.3, 90.0)
	var points := PackedVector2Array()
	for i in 25:
		var t := i / 24.0
		points.append(a.lerp(controle, t).lerp(controle.lerp(b, t), t))
	return points


func _chemins(au_dessus: bool) -> void:
	## Un chemin par paire de groupes reliée par des ponts, d'autant plus épais
	## qu'il y a de ponts. Entre bâtiments voisins, un chemin droit sous les
	## bâtiments ; entre bâtiments éloignés, un arc tracé par-dessus le plan,
	## pour que son étiquette ne passe sous aucun bâtiment. Cloisonné : rien.
	var ponts := _ponts_par_paire()
	var places := []
	for cle in ponts:
		var g: PackedStringArray = (cle as String).split("|")
		if not (zones.has(g[0]) and zones.has(g[1])):
			continue
		var droit := _voisins_sur_plan(g[0], g[1])
		if droit == au_dessus:
			continue
		var a: Vector2 = (zones[g[0]] as Rect2).get_center()
		var b: Vector2 = (zones[g[1]] as Rect2).get_center()
		var n := int(ponts[cle])
		var lieu: Vector2
		if droit:
			draw_line(a, b, CHEMIN, clampf(2.0 + 1.5 * n, 3.0, 8.0), true)
			# Le milieu d'un chemin droit tombe entre les deux bâtiments.
			var bord_a := (zones[g[0]] as Rect2)
			var bord_b := (zones[g[1]] as Rect2)
			lieu = (bord_a.get_center().lerp(bord_b.get_center(), 0.5))
		else:
			var points := _arc(a, b)
			draw_polyline(points, Color(CHEMIN.darkened(0.2), 0.75), clampf(1.0 + 0.6 * n, 1.5, 4.0), true)
			lieu = points[12]
		for deja in places:
			if (deja as Vector2).distance_to(lieu) < 18.0:
				lieu.y += 18.0
		places.append(lieu)
		_pastille(lieu, "%d pont%s" % [n, "s" if n > 1 else ""])


func _batiment(nom: String) -> void:
	## Un bâtiment en léger relief : ombre au sol, façade, toit et flanc.
	var z: Rect2 = zones[nom]
	var d := PROFONDEUR
	var hg := z.position
	var hd := Vector2(z.end.x, z.position.y)
	var bd := z.end
	var bg := Vector2(z.position.x, z.end.y)
	draw_colored_polygon(PackedVector2Array([bg + Vector2(6, 0), bd + Vector2(6, 0),
		bd + Vector2(14, 8), bg + Vector2(14, 8)]), Color(0, 0, 0, 0.06))
	draw_colored_polygon(PackedVector2Array([hg, hd, hd + d, hg + d]), TRAIT.darkened(0.04))
	draw_colored_polygon(PackedVector2Array([hd, bd, bd + d, hd + d]), TRAIT.darkened(0.16))
	draw_rect(z, Color(1, 1, 1, 0.97))
	draw_rect(Rect2(z.position, Vector2(z.size.x, 28)), Color(TRAIT, 0.6))
	draw_rect(z, TRAIT.darkened(0.12), false, 1.2)
	var porteurs := 0
	var total := 0
	for a in etat.get("agents", []):
		if a.get("groupe", "") == nom:
			total += 1
			if a.get("porte", false):
				porteurs += 1
	_txt(z.position + Vector2(10, 20), _groupe(nom), 13, ENCRE, true)
	var compte := "%d/%d portent" % [porteurs, total]
	_txt(z.position + Vector2(z.size.x - 10 - _largeur(compte, 11), 20), compte, 11, DOUX)


func _groupes() -> void:
	if zones.is_empty():
		return
	draw_rect(Rect2(ZONE_GROUPES.position - Vector2(10, 22),
		ZONE_GROUPES.size + Vector2(20 + PROFONDEUR.x, 30)), SOL)
	_chemins(false)
	for nom in ordre_groupes:
		_batiment(nom)
	_chemins(true)
	if voir_reseau:
		_reseau()
	else:
		_regards()
	_messages()
	for a in etat.get("agents", []):
		_etudiant(a)


func _reseau() -> void:
	## Liens forts dans le groupe en trait plein, ponts faibles en pointillé.
	## Avec un étudiant sélectionné, seuls ses liens restent nets : on voit
	## qui il observe et à qui il peut écrire.
	for l in etat.get("liens", []):
		var a: String = l["a"]
		var b: String = l["b"]
		if not (positions.has(a) and positions.has(b)):
			continue
		var fort: bool = l["type"] == "fort"
		var a_lui := selection != "" and (a == selection or b == selection)
		var couleur := Color(0.39, 0.38, 0.48, 0.30 if fort else 0.16)
		if selection != "" and not a_lui:
			couleur.a *= 0.35
		elif a_lui:
			couleur = Color(ENCRE, 0.8 if fort else 0.55)
		var largeur := (2.0 if a_lui else 1.2) if fort else (1.5 if a_lui else 1.0)
		if fort:
			draw_line(positions[a], positions[b], couleur, largeur, true)
		else:
			draw_dashed_line(positions[a], positions[b], couleur, largeur, 6.0)


func _regards() -> void:
	## Qui a vu qui aujourd'hui (perception.v2). Un regard vers quelqu'un qui
	## porte le ruban prend la couleur de son sens ; vers quelqu'un qui ne le
	## porte pas, il reste gris et discret. Le jour nouveau apparaît en fondu.
	var categorie := {}
	for a in etat.get("agents", []):
		categorie[a["id"]] = a.get("categorie", "aucun_sens")
	var fondu := clampf(regards_age / 0.6, 0.0, 1.0)
	for r in etat.get("regards", []):
		var voit: String = r[0]
		var qui: String = r[1]
		if not (positions.has(voit) and positions.has(qui)):
			continue
		var porte: bool = r[3]
		var c: Color = COULEURS.get(categorie.get(qui, ""), DOUX) if porte else DOUX
		var alpha := 0.32 if porte else 0.12
		var largeur := 1.2
		if selection != "":
			if voit == selection:
				alpha = 0.9
				largeur = 2.0
			else:
				alpha *= 0.3
		var de: Vector2 = positions[voit]
		var vers: Vector2 = positions[qui]
		draw_line(de, vers, Color(c, alpha * fondu), largeur, true)
		draw_circle(de.lerp(vers, 0.85), 2.5 if largeur > 1.5 else 1.8, Color(c, alpha * fondu))


func _messages() -> void:
	for v in vols:
		if not (positions.has(v["de"]) and positions.has(v["vers"])):
			continue
		var de: Vector2 = positions[v["de"]]
		var vers: Vector2 = positions[v["vers"]]
		var avance := 1.0 - float(v["reste"]) / DUREE_VOL
		var c: Color = v["couleur"]
		draw_line(de, de.lerp(vers, avance), Color(c, 0.5), 2.0, true)
		draw_circle(de.lerp(vers, avance), 5.0, c)
	for o in ondes:
		var avance := 1.0 - float(o["reste"]) / DUREE_ONDE
		var c: Color = o["couleur"]
		draw_arc(o["centre"], 14.0 + avance * 70.0, 0, TAU, 40,
			Color(c, 0.7 * (1.0 - avance)), 2.5)


func _etudiant(a: Dictionary) -> void:
	var id: String = a["id"]
	if not positions.has(id):
		return
	var centre: Vector2 = positions[id]
	var r: float = rayons[id]
	var cat: String = a.get("categorie", "aucun_sens")
	var couleur: Color = COULEURS.get(cat, DOUX)
	var estompe: bool = selection != "" and id != selection and not voisins.get(selection, {}).has(id)
	if eclats.has(id):
		var e: float = eclats[id] / DUREE_ECLAT
		draw_circle(centre, r + 4 + 10 * e, Color(couleur, 0.35 * e))
	if estompe:
		couleur = couleur.lerp(FOND, 0.55)
	draw_circle(centre + Vector2(2, 3), r, Color(0, 0, 0, 0.07))   # ombre
	if a.get("porte", false):
		draw_circle(centre, r, couleur)
		# Le ruban : un arc autour du poignet, de la couleur du sens.
		draw_arc(centre, r + 4, 0.6, 2.54, 24, couleur.darkened(0.25), 3.0)
	else:
		draw_circle(centre, r, Color(1, 1, 1, 1))
		draw_arc(centre, r, 0, TAU, 28, couleur, 2.0)
	if not a.get("valide", true):
		# Agent dont la dernière réponse était inexploitable (exigence A4).
		draw_arc(centre, r + 8, 0, TAU, 28, ALERTE, 1.5)
	if id == selection:
		draw_arc(centre, r + 11, 0, TAU, 32, ENCRE, 2.0)
	var lettres: String = etiquettes.get(id, "?")
	var taille := int(clampf(r * 0.62, 9, 13))
	var encre: Color = Color(1, 1, 1) if a.get("porte", false) else ENCRE
	if estompe:
		encre = encre.lerp(FOND, 0.5)
	if r >= 9.0:
		_txt(centre + Vector2(-_largeur(lettres, taille, true) / 2.0, taille * 0.36), lettres,
			taille, encre, true)
	if noms_sous:
		var prenom := _prenom(str(a.get("nom", "")))
		_txt(centre + Vector2(-_largeur(prenom, 10) / 2.0, r + 15), prenom, 10,
			DOUX.lerp(FOND, 0.5) if estompe else DOUX)


func _infobulle() -> void:
	if survol == "" or not positions.has(survol):
		return
	var a := _agent(survol)
	if a.is_empty():
		return
	var cat: String = a.get("categorie", "aucun_sens")
	var texte := "%s, %s, %s" % [_prenom(str(a.get("nom", ""))),
		PROFILS.get(a.get("profil", ""), a.get("profil", "")), LIBELLES.get(cat, cat)]
	var p: Vector2 = positions[survol] + Vector2(float(rayons[survol]) + 8, -float(rayons[survol]) - 4)
	var l := _largeur(texte, 12) + 14
	p.x = minf(p.x, PANNEAU_X - l - 4)
	draw_rect(Rect2(p - Vector2(0, 15), Vector2(l, 21)), Color(ENCRE, 0.92))
	_txt(p + Vector2(7, 0), texte, 12, Color.WHITE)


# ------------------------------------------------------------------ courbe


func _trace_courbe() -> Rect2:
	## La zone où la courbe est tracée : x = jour, y = adoption.
	return Rect2(COURBE.position.x + 46, COURBE.position.y + 34,
		COURBE.size.x - 62, COURBE.size.y - 56)


func _x_du_jour(t_sim: float) -> float:
	var trace := _trace_courbe()
	return trace.position.x + clampf(t_sim / float(_jours() * JOUR), 0.0, 1.0) * trace.size.x


func _courbe() -> void:
	## La courbe de vie de la tendance, en cours de construction, sur l'axe
	## du run entier. Chaque point prend la couleur du sens dominant : on lit
	## QUAND le ruban a changé de signification. Les injections (D3) et les
	## contre-tendances y sont repérées. En rejeu, un curseur marque le jour
	## affiché, et un clic sur la courbe va à un autre jour.
	var x := COURBE.position.x
	var y := COURBE.position.y
	draw_rect(COURBE, Color(1, 1, 1, 0.8))
	draw_rect(COURBE, TRAIT, false, 1.0)
	_txt(Vector2(x + 12, y + 20), "vie de la tendance", 12, DOUX, true)
	_contre_tendance(Vector2(x + 150, y + 6))
	_lecture(Vector2(x + COURBE.size.x - 12, y + 6))

	var hist: Array = etat.get("historique", [])
	if hist.size() < 2:
		_txt(Vector2(x + 12, y + 80), "en attente de données...", 12, DOUX)
		return
	var trace := _trace_courbe()
	var bas := trace.end.y
	var haut := trace.position.y
	for part in [0.0, 0.5, 1.0]:
		var yy: float = bas - part * (bas - haut)
		draw_line(Vector2(trace.position.x - 2, yy), Vector2(trace.end.x, yy), TRAIT, 1.0)
		_txt(Vector2(x + 10, yy + 4), "%d %%" % int(part * 100), 10, DOUX)
	for j in [0, _jours() / 2, _jours()]:
		var jx := _x_du_jour(j * JOUR)
		var nom: String = "J%d" % int(j)
		_txt(Vector2(jx - _largeur(nom, 9) / 2.0, bas + 14), nom, 9, DOUX)

	var points := PackedVector2Array()
	var pic := 0
	for i in hist.size():
		var t: float = float(hist[i].get("taux_adoption", 0.0))
		points.append(Vector2(_x_du_jour(float(hist[i].get("t_sim", 0))), bas - t * (bas - haut)))
		if t > float(hist[pic].get("taux_adoption", 0.0)):
			pic = i

	for inj in etat.get("injections", []):
		var ix := _x_du_jour(float(inj.get("t_sim", 0)))
		draw_dashed_line(Vector2(ix, haut - 4), Vector2(ix, bas), ALERTE, 1.0, 4.0)
		var nom: String = INJECTIONS.get(str(inj.get("nature", "")), str(inj.get("nature", "")))
		_txt(Vector2(ix + 3, haut + 8), nom, 10, ALERTE)
	for ct in etat.get("contre_tendances", []):
		var cx := _x_du_jour(float(ct.get("t_sim", 0)))
		var c: Color = COULEURS["ironie"] if ct.get("nature", "") == "ironie" else ALERTE
		draw_colored_polygon(PackedVector2Array([Vector2(cx - 5, haut - 8),
			Vector2(cx + 5, haut - 8), Vector2(cx, haut - 1)]), c)

	draw_polyline(points, DOUX, 2.0, true)
	var rayon_point := clampf(300.0 / hist.size(), 2.0, 4.0)
	for i in hist.size():
		var dom: String = hist[i].get("sens_dominant", "aucun_sens")
		draw_circle(points[i], rayon_point, COULEURS.get(dom, DOUX))
	# Le pic, que la définition du cycle compare à la fin du run.
	var taux_pic: float = hist[pic].get("taux_adoption", 0.0)
	if taux_pic > 0.0:
		draw_arc(points[pic], rayon_point + 3, 0, TAU, 20, ENCRE, 1.2)
		_txt(points[pic] + Vector2(6, -6), "pic %d %%" % int(round(taux_pic * 100)), 10, ENCRE)
	if etat.has("rejeu"):
		var cx := _x_du_jour(float(_jour() * JOUR))
		draw_line(Vector2(cx, haut - 2), Vector2(cx, bas), Color(ENCRE, 0.6), 1.5)


func _contre_tendance(coin: Vector2) -> void:
	## Le bandeau de contre-tendance : la dernière repérée par le pont (au
	## moins 15 % du campus le même jour, qui passe à l'ironie ou abandonne).
	## Il s'allume quand elle apparaît, puis reste affiché en plus discret.
	var liste: Array = etat.get("contre_tendances", [])
	if liste.is_empty():
		return
	var ct: Dictionary = liste[liste.size() - 1]
	var noms: Array = ct.get("qui", [])
	var qui := ", ".join(PackedStringArray(noms.slice(0, 3).map(func(n): return _prenom(str(n)))))
	if noms.size() > 3:
		qui += " +%d" % (noms.size() - 3)
	var quoi: String = "passent à l'ironie" if ct.get("nature", "") == "ironie" else "abandonnent ensemble"
	var t := int(ct.get("t_sim", 0))
	var texte := "contre-tendance, jour %d : %d %s (%s)" % [t / JOUR, noms.size(), quoi, qui]
	var c: Color = COULEURS["ironie"] if ct.get("nature", "") == "ironie" else ALERTE
	var vif := alerte / DUREE_ALERTE
	var l := _largeur(texte, 11, true) + 16.0
	var r := Rect2(coin, Vector2(l, 20))
	draw_rect(r, Color(c, 0.12 + 0.8 * vif))
	draw_rect(r, c, false, 1.0)
	_txt(r.position + Vector2(8, 14), texte, 11, c.lerp(Color.WHITE, vif), true)


func _lecture(coin_droit: Vector2) -> void:
	## Le contrôle du rejeu : pause ou lecture, et le jour affiché.
	bouton_lecture = Rect2()
	if not etat.has("rejeu"):
		return
	var r: Dictionary = etat["rejeu"]
	var en_pause: bool = r.get("pause", false)
	var b := Rect2(coin_droit - Vector2(22, 0), Vector2(22, 20))
	bouton_lecture = b
	draw_rect(b, Color(1, 1, 1))
	draw_rect(b, DOUX, false, 1.0)
	var c := b.get_center()
	if en_pause:
		draw_colored_polygon(PackedVector2Array([c + Vector2(-4, -6), c + Vector2(6, 0),
			c + Vector2(-4, 6)]), ENCRE)
	else:
		draw_rect(Rect2(c + Vector2(-5, -6), Vector2(3, 12)), ENCRE)
		draw_rect(Rect2(c + Vector2(2, -6), Vector2(3, 12)), ENCRE)
	var texte := "rejeu, jour %d/%d%s   (flèches, espace)" % [_jour(), int(r.get("jours", 0)),
		", en pause" if en_pause else ""]
	_txt(Vector2(b.position.x - 8 - _largeur(texte, 11), b.position.y + 14), texte, 11, DOUX)


func _repartition() -> void:
	## Ce que le ruban veut dire, maintenant, pour tout le campus.
	## Une barre empilée : si une couleur occupe toute la largeur, le campus
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
	var y := 692.0
	var l := 854.0
	_txt(Vector2(x, y - 6), "ce que le ruban veut dire, maintenant, sur tout le campus", 12, DOUX)
	var curseur := x
	for cle in ORDRE_SENS:
		var n := int(repartition.get(cle, 0))
		if n == 0:
			continue
		var large: float = l * float(n) / float(total)
		draw_rect(Rect2(curseur, y, large, 14), COULEURS.get(cle, DOUX))
		var etiquette := "%s %d" % [LIBELLES.get(cle, cle), n]
		if large > _largeur(etiquette, 10) + 10:
			_txt(Vector2(curseur + 5, y + 11), etiquette, 10, Color(1, 1, 1, 0.95))
		curseur += large


func _boutons() -> void:
	var possible := _injections_possibles()
	var titre := "bousculer le monde"
	if etat.has("rejeu"):
		titre += "   (rejeu : un run enregistré ne se bouscule pas)"
	elif etat.get("modele_social", "v1") == "v2":
		titre += "   (modèle v2 : injections prévues à l'étape 7 de la migration)"
	_txt(Vector2(28, 728), titre, 12, DOUX)
	for b in boutons:
		var r: Rect2 = b["rect"]
		var dedans := r.has_point(get_global_mouse_position())
		draw_rect(r, Color(1, 1, 1, 1.0 if possible and dedans else 0.9))
		draw_rect(r, ENCRE if possible and dedans else TRAIT, false, 1.0)
		_txt(r.position + Vector2(14, 21), b["titre"], 13,
			ENCRE if possible else TRAIT.darkened(0.2))


# ------------------------------------------------------------------ panneau


func _agent(id: String) -> Dictionary:
	for a in etat.get("agents", []):
		if a["id"] == id:
			return a
	return {}


func _panneau() -> void:
	var x := PANNEAU_X
	var y := 104.0
	var l := 372.0
	var bas := 704.0
	draw_rect(Rect2(x, y, l, bas - y), Color(1, 1, 1, 0.88))
	draw_rect(Rect2(x, y, l, bas - y), TRAIT, false, 1.0)
	tableau = {}
	var agent := _agent(selection)
	if agent.is_empty():
		y = _sens_par_groupe(x + 16, y + 24, l - 32)
		_fil(x + 16, y + 22, l - 32, bas)
		return
	y += 28
	var prenom := _prenom(str(agent.get("nom", "")))
	_txt(Vector2(x + 16, y), prenom, 17, ENCRE, true)
	var profil: String = PROFILS.get(agent.get("profil", ""), str(agent.get("profil", "")))
	_txt(Vector2(x + 26 + _largeur(prenom, 17, true), y), profil, 13, DOUX)
	y += 20
	var vs: Dictionary = voisins.get(selection, {})
	var details := "%s, moteur %s" % [_groupe(str(agent.get("groupe", ""))), agent.get("moteur", "")]
	if not vs.is_empty():
		var forts := 0
		for v in vs:
			if vs[v] == "fort":
				forts += 1
		details += ", %d proches, %d ponts" % [forts, vs.size() - forts]
	_txt(Vector2(x + 16, y), details, 12, DOUX)
	y += 26
	var cat: String = agent.get("categorie", "aucun_sens")
	var porte: bool = agent.get("porte", false)
	_txt(Vector2(x + 16, y), ("porte le ruban" if porte else "ne le porte pas")
		+ ", pour lui : " + LIBELLES.get(cat, cat), 14, COULEURS.get(cat, ENCRE), true)
	y += 6
	if agent.get("termes") != null:
		y = _croyances(agent, x + 16, y + 18, l - 32)
		y = _score(agent["termes"], x + 16, y + 14, l - 32)
		y = _vu(agent, x + 16, y + 8, l - 32)
		y = _sources(agent, x + 16, y + 6, l - 32, bas)
	else:
		y += 16
		y = _bloc(x + 16, y, l - 32, _lisible(str(agent.get("sens", ""))), bas)
		y += 8
		_txt(Vector2(x + 16, y), "dernière décision", 12, DOUX)
		y += 18
		y = _bloc(x + 16, y, l - 32, _lisible(str(agent.get("raison", ""))), bas)
	y += 10
	if y < bas - 40:
		_txt(Vector2(x + 16, y), "mémoire", 12, DOUX)
		y += 18
		var memoire: Array = agent.get("memoire", [])
		for i in range(memoire.size() - 1, -1, -1):
			if y > bas - 20:
				break
			var m: Dictionary = memoire[i]
			y = _bloc(x + 16, y, l - 32, "%s  %s" % [m.get("t_sim_lisible", ""),
				_lisible(str(m.get("fait", "")))], bas, 2)
			y += 2


func _sens_par_groupe(x: float, y: float, l: float) -> float:
	## Ce que le ruban veut dire dans chaque groupe, jour par jour (exigence
	## B1) : une ligne par groupe, une colonne par relevé, la couleur du sens
	## dominant du groupe, d'autant plus franche qu'il y est majoritaire. On
	## voit un groupe garder son sens pendant qu'un autre bascule.
	_txt(Vector2(x, y), "Ce que le ruban veut dire, groupe par groupe", 13, ENCRE, true)
	y += 12
	var releves: Array = etat.get("sens_groupes", [])
	var colonnes := maxi(_jours() + 1, releves.size())
	var etiquette := 96.0
	var largeur := l - etiquette
	var colonne := largeur / colonnes
	var hauteur := 17.0
	var origine := Vector2(x + etiquette, y)
	for i in ordre_groupes.size():
		var g: String = ordre_groupes[i]
		var ly := y + i * (hauteur + 3)
		_txt(Vector2(x, ly + 12), _groupe(g), 11, DOUX)
		draw_rect(Rect2(origine.x, ly, largeur, hauteur), Color(TRAIT, 0.35))
		for k in releves.size():
			var gr: Dictionary = releves[k].get("groupes", {}).get(g, {})
			if gr.is_empty():
				continue
			var k_jour := int(releves[k].get("t_sim", 0)) / JOUR
			var c: Color = COULEURS.get(gr.get("dominant", ""), DOUX)
			var part: float = gr.get("part", 0.0)
			draw_rect(Rect2(origine.x + k_jour * colonne, ly, maxf(colonne - 0.5, 1.0), hauteur),
				Color(c, 0.3 + 0.7 * part))
	var bas := y + ordre_groupes.size() * (hauteur + 3)
	tableau = {"rect": Rect2(origine, Vector2(largeur, bas - y)), "colonne": colonne}
	if not releves.is_empty():
		var cx := origine.x + (_jour() + 0.5) * colonne
		draw_line(Vector2(cx, y - 3), Vector2(cx, bas), Color(ENCRE, 0.7), 1.2)
	for j in [0, _jours() / 2, _jours()]:
		var nom: String = "J%d" % int(j)
		var jx: float = origine.x + (j + 0.5) * colonne
		_txt(Vector2(clampf(jx - _largeur(nom, 9) / 2.0, origine.x, x + l - 14), bas + 11),
			nom, 9, DOUX)
	y = bas + 26
	var aide := "Cliquez sur un étudiant pour voir ce qu'il a vu et pourquoi il a choisi."
	return _bloc(x, y, l, aide, 9999.0, 2, DOUX, 11)


func _croyances(agent: Dictionary, x: float, y: float, l: float) -> float:
	## Les deux croyances du modèle v2 : ce que le ruban veut dire pour lui,
	## et ce qu'il croit que le campus en pense. Plus la confiance est haute,
	## moins il change d'avis en entendant ses proches.
	var percu: String = agent.get("sens_percu", "aucun_sens")
	var question := "croit que le campus le lit comme :"
	_txt(Vector2(x, y), question, 12, DOUX)
	_txt(Vector2(x + 6 + _largeur(question, 12), y), LIBELLES.get(percu, percu), 12,
		COULEURS.get(percu, ENCRE), true)
	y += 18
	var confiance: float = float(agent.get("confiance", 0.0))
	_txt(Vector2(x, y), "confiance en son sens", 12, DOUX)
	var barre := Rect2(x + 150, y - 9, l - 190, 8)
	draw_rect(barre, TRAIT)
	draw_rect(Rect2(barre.position, Vector2(barre.size.x * confiance, barre.size.y)), DOUX)
	_txt(Vector2(barre.end.x + 6, y), "%.2f" % confiance, 11, DOUX)
	return y


func _score(termes: Dictionary, x: float, y: float, l: float) -> float:
	## La règle appliquée, terme par terme (exigence D2 pour un agent à
	## règles) : chaque barre part de zéro, à droite ce qui pousse à porter,
	## à gauche ce qui retient. Il porte demain si S > 0.
	_txt(Vector2(x, y), "pourquoi : porte demain si S > 0", 12, DOUX)
	y += 8
	var lignes := [
		["appartenance", "a × E", 1.0], ["nouveaute", "nouveauté", 1.0],
		["distinction", "distinction", -1.0], ["lassitude", "lassitude", -1.0],
		["seuil", "seuil", -1.0], ["bruit", "bruit", 1.0], ["S", "S", 1.0],
	]
	var axe := x + 92.0 + (l - 150.0) / 2.0
	var echelle := (l - 150.0) / 2.0  # une barre pleine = 1
	for ligne in lignes:
		var v: float = float(termes.get(ligne[0], 0.0)) * float(ligne[2])
		y += 17
		var est_s: bool = ligne[0] == "S"
		if est_s:
			draw_line(Vector2(x, y - 13), Vector2(x + l, y - 13), TRAIT, 1.0)
			y += 2
		_txt(Vector2(x, y), ligne[1], 12, ENCRE if est_s else DOUX, est_s)
		var c := VERT if v > 0 else ALERTE
		if absf(v) < 1e-6:
			c = TRAIT
		var w := clampf(v, -1.0, 1.0) * echelle
		var epaisseur := 10.0 if est_s else 8.0
		draw_rect(Rect2(minf(axe, axe + w), y - 10.0, absf(w), epaisseur), c)
		_txt(Vector2(x + l - 44, y), "%+.2f" % v, 11, ENCRE if est_s else DOUX, est_s)
	draw_line(Vector2(axe, y - 17 * lignes.size() - 2), Vector2(axe, y + 2), DOUX, 1.0)
	y += 16
	var e: float = float(termes.get("E", 0.0))
	_txt(Vector2(x, y), "E %.2f (part vue portant le ruban)   R %.2f   P %.0f"
		% [e, float(termes.get("R", 0.0)), float(termes.get("P", 0.0))], 11, DOUX)
	return y


func _vu(agent: Dictionary, x: float, y: float, l: float) -> float:
	var vu = agent.get("vu")
	if typeof(vu) != TYPE_DICTIONARY:
		return y
	y += 10
	var noms: Array = vu.get("porteurs_noms", [])
	var texte := "a vu %d personnes, %d avec le ruban" % [int(vu.get("personnes", 0)),
		int(vu.get("porteurs", 0))]
	if not noms.is_empty():
		texte += " (%s)" % ", ".join(PackedStringArray(noms.slice(0, 4)))
	texte += ", lu %d messages et %d publications" % [int(vu.get("messages", 0)),
		int(vu.get("publications", 0))]
	return _bloc(x, y, l, _lisible(texte), 700.0, 2) - 4


func _sources(agent: Dictionary, x: float, y: float, l: float, bas: float) -> float:
	## Ce qui a fait changer ses croyances la dernière fois, cité par id.
	var sources: Array = agent.get("sources", [])
	if sources.is_empty():
		return y
	y += 12
	_txt(Vector2(x, y), "%s, a changé d'avis à cause de" % agent.get("sources_quand", ""),
		12, DOUX)
	y += 16
	for i in mini(3, sources.size()):
		var s: Dictionary = sources[i]
		y = _bloc(x, y, l, "%s  %s" % [s.get("id", ""), _lisible(str(s.get("texte", "")))], bas, 2)
	if sources.size() > 3:
		_txt(Vector2(x, y), "et %d autres" % (sources.size() - 3), 11, DOUX)
		y += 14
	return y


func _fil(x: float, y: float, l: float, bas: float) -> void:
	## Le fil des derniers messages, du plus récent au plus ancien. Le pont
	## regroupe les messages identiques : "c'est dépassé ×12, J24 à J26".
	_txt(Vector2(x, y), "Réseau interne", 13, ENCRE, true)
	y += 20
	var fil: Array = etat.get("fil", [])
	if fil.is_empty():
		_txt(Vector2(x, y), "personne n'a encore parlé.", 12, DOUX)
	for i in range(fil.size() - 1, -1, -1):
		if y > bas - 20:
			break
		var m: Dictionary = fil[i]
		var n := int(m.get("n", 1))
		var auteurs: Array = m.get("auteurs", [m.get("auteur", "")])
		var qui := ", ".join(PackedStringArray(auteurs.slice(0, 2).map(func(a): return _prenom(str(a)))))
		if auteurs.size() > 2:
			qui += " +%d" % (auteurs.size() - 2)
		if n == 1 and m.get("portee", "campus") == "personne" and m.get("destinataire") != null:
			qui += " à %s" % _prenom(str(m["destinataire"]))
		var quand := str(m.get("t_sim_lisible", "")).substr(0, 3)
		if n > 1:
			quand = "×%d, %s à %s" % [n, str(m.get("premier", "")).substr(0, 3), quand]
		var cat := str(m.get("categorie", ""))
		if COULEURS.has(cat):
			draw_rect(Rect2(x - 8, y - 11, 3, 28), COULEURS[cat])
		_txt(Vector2(x, y), "%s   %s" % [quand, qui], 11, DOUX)
		y += 15
		y = _bloc(x, y, l, _lisible(str(m.get("texte", ""))), bas, 2)
		y += 6


func _bloc(x: float, y: float, largeur: float, texte: String, bas := 9999.0,
		max_lignes := 4, couleur := ENCRE, taille := 12) -> float:
	## Texte coupé en lignes à la largeur réelle de la police.
	if texte == "":
		return y
	var mots := texte.split(" ")
	var ligne := ""
	var lignes := 0
	var pas := taille + 4
	for mot in mots:
		var essai: String = mot if ligne == "" else ligne + " " + mot
		if _largeur(essai, taille) > largeur and ligne != "":
			if lignes == max_lignes - 1:
				ligne += "…"
				break
			_txt(Vector2(x, y), ligne, taille, couleur)
			y += pas
			lignes += 1
			if y > bas:
				return y
			ligne = mot
		else:
			ligne = essai
	if ligne != "" and y <= bas:
		_txt(Vector2(x, y), ligne, taille, couleur)
		y += pas
	return y
