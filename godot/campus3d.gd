extends SubViewportContainer
## Vue 3D du campus de Tessaline, posée à la place du plan 2D.
##
## Mêmes règles que le plan : la vue AFFICHE l'état reçu du pont, elle ne
## simule rien. Chaque groupe est un bâtiment, les étudiants se tiennent sur
## le parvis de leur bâtiment, les ponts du réseau sont les chemins au sol et
## les traits sont les regards du jour (perception.v2). Personne ne se déplace :
## le modèle n'a pas d'espace, le "lieu" où l'on se croise est le groupe. C'est
## pour cela qu'il n'y a ni navigation ni NavigationServer3D : un trajet affiché
## serait un déplacement qu'aucun événement du run ne contient (F6).
##
## Lecture : la couleur du corps dit ce que le ruban veut dire pour l'étudiant ;
## corps franc et anneau lumineux au poignet : il le porte ; corps pâle sans
## anneau : il ne le porte pas. Liseré rouge au sol : dernière réponse
## inexploitable (A4).
##
## Rendu Forward+ : SDFGI, brouillard volumétrique, SSAO, SSIL, matériaux PBR,
## ombres douces. Le SDFGI ne retient que la géométrie STATIQUE : le décor
## (sol, bâtiments, fenêtres et lampes émissives) éclaire le campus ; les
## étudiants, qui sautent et changent de couleur, sont en GI dynamique : ils
## reçoivent la lumière indirecte sans en émettre, sinon le SDFGI garderait
## l'ancienne couleur d'un étudiant après son changement d'avis. Touche G
## (scène 2D) : rendu léger, pour une machine qui peine pendant la démo.
##
## Coût par image : rien quand rien ne change. Les couleurs et les traits se
## recalculent sur un changement d'état, de sélection ou de survol ; seules
## les animations en cours font tourner _process. Un étudiant hors du champ de
## la caméra (VisibleOnScreenNotifier3D) n'est ni recoloré, ni animé, ni testé
## au survol.
##
## Souris : glisser pour tourner autour du campus, molette pour zoomer, clic
## sur un étudiant pour l'inspecter (le panneau 2D affiche sa fiche).

signal agent_clique(id: String)

const COLONNE := 11.0       # écart entre bâtiments, en mètres
const RANG := 13.0
const BATIMENT := Vector3(7.0, 3.0, 4.5)
const PAS_AGENT := 0.95
const DUREE_VOL := 0.9
const DUREE_ONDE := 1.2
const DUREE_SAUT := 0.6
const HAUTEUR_TRAIT := 1.05

# Émission : au-dessus de 1, une surface dépasse le blanc et passe le seuil du
# glow ; statique, elle éclaire aussi son entourage par le SDFGI.
const EMISSION_RUBAN := 2.2
const EMISSION_RUBAN_ESTOMPE := 0.4
const EMISSION_FENETRE := 1.4
const EMISSION_LAMPE := 4.0
const EMISSION_BILLE := 3.0
const EMISSION_ONDE := 2.0
const BROUILLARD := 0.006   # densité par mètre : à 40 m, environ 20 % de voile

var couleurs := {}
var plan := {}
var police: Font
var groupes_lisibles := {}
var lisible := Callable()   # accents des prénoms, fournis par la scène 2D

# La scène 2D réécrit ces deux valeurs à chaque image : le setter ne réveille
# la vue que si elles changent vraiment.
var selection := "":
	set(valeur):
		if valeur != selection:
			selection = valeur
			_reveiller()
var voir_reseau := false:
	set(valeur):
		if valeur != voir_reseau:
			voir_reseau = valeur
			_reveiller()
var survol := ""
var haute_qualite := true

var _vp: SubViewport
var _monde: Node3D
var _env: Environment
var _soleil: DirectionalLight3D
var _camera: Camera3D
var _batiments: Node3D
var _chemins: Node3D
var _agents: Node3D
var _effets: Node3D
var _traits: MeshInstance3D
var _trait_mesh: ImmediateMesh
var _trait_mat: StandardMaterial3D
var _anneau_selection: MeshInstance3D

var _comptes := {}         # groupe -> Label3D "3/7 portent"
var _signature := ""
var _signature_chemins := ""
var _noeuds := {}          # id -> {racine, corps, mat, anneau, mat_anneau, nom, alerte, vu}
var _places := {}          # id -> Vector3 (pieds)
var _hors_champ := {}      # id -> true, tenu par les VisibleOnScreenNotifier3D
var _etat := {}
var _voisins := {}
var _sale := true          # couleurs et traits à recalculer

var _cible := Vector3(0, 0, 2.5)   # centre des parvis
var _lacet := 0.0          # rotation autour de la verticale, en radians
var _tangage := deg_to_rad(52.0)
var _distance := 30.0
var _glisse := false
var _depart_clic := Vector2.ZERO

var _vols := []            # {de, vers, reste, noeud}
var _ondes := []           # {noeud, mat, reste}
var _sauts := {}           # id -> reste


func _ready() -> void:
	stretch = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	_vp = SubViewport.new()
	_vp.own_world_3d = true
	_vp.msaa_3d = Viewport.MSAA_4X
	_vp.use_debanding = true             # dégradés du brouillard et du ciel sans paliers
	_vp.positional_shadow_atlas_size = 4096
	_vp.handle_input_locally = false
	add_child(_vp)
	_monde = Node3D.new()
	_vp.add_child(_monde)

	_env = _environnement()
	var we := WorldEnvironment.new()
	we.environment = _env
	_monde.add_child(we)

	_soleil = DirectionalLight3D.new()
	_soleil.rotation_degrees = Vector3(-55, -35, 0)
	_soleil.light_energy = 1.1
	_soleil.light_color = Color("#fff4e6")
	_soleil.shadow_enabled = true
	_soleil.light_angular_distance = 1.2      # pénombre PCSS : ombres douces
	_soleil.shadow_blur = 1.5
	_soleil.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	_soleil.directional_shadow_max_distance = 90.0   # le campus entier, pas plus
	_soleil.directional_shadow_blend_splits = true
	_soleil.light_volumetric_fog_energy = 1.0         # rais de lumière dans le brouillard
	_monde.add_child(_soleil)

	# Le sol est une dalle épaisse plutôt qu'un plan : le SDFGI voit mieux une
	# géométrie qui a un volume, et la lumière ne fuit pas dessous.
	var sol := MeshInstance3D.new()
	var dalle := BoxMesh.new()
	dalle.size = Vector3(60, 0.2, 50)
	sol.mesh = dalle
	sol.position = Vector3(0, -0.1, 0)
	sol.material_override = _matiere(Color("#e3e8dc"), 0.95)
	_monde.add_child(sol)

	_camera = Camera3D.new()
	_camera.fov = 38.0
	_monde.add_child(_camera)
	_placer_camera()

	_batiments = Node3D.new()
	_chemins = Node3D.new()
	_agents = Node3D.new()
	_effets = Node3D.new()
	for n in [_batiments, _chemins, _agents, _effets]:
		_monde.add_child(n)

	_trait_mesh = ImmediateMesh.new()
	_traits = MeshInstance3D.new()
	_traits.mesh = _trait_mesh
	_sans_ombre_ni_gi(_traits)
	_trait_mat = StandardMaterial3D.new()
	_trait_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_trait_mat.vertex_color_use_as_albedo = true
	_trait_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_monde.add_child(_traits)

	_anneau_selection = MeshInstance3D.new()
	var t := TorusMesh.new()
	t.inner_radius = 0.42
	t.outer_radius = 0.52
	_anneau_selection.mesh = t
	_anneau_selection.material_override = _repere(Color("#24212e"))
	_sans_ombre_ni_gi(_anneau_selection)
	_anneau_selection.visible = false
	_monde.add_child(_anneau_selection)

	regler_qualite(haute_qualite)
	set_process(false)


func _environnement() -> Environment:
	var env := Environment.new()
	# Ciel procédural aux teintes du fond de l'interface : il éclaire la scène
	# (lumière ambiante, reflets, et le SDFGI lit sa lumière).
	var ciel := ProceduralSkyMaterial.new()
	ciel.sky_top_color = Color("#b8c7dc")
	ciel.sky_horizon_color = Color("#eef0f5")
	ciel.ground_bottom_color = Color("#d9dccf")
	ciel.ground_horizon_color = Color("#eef0f5")
	var sky := Sky.new()
	sky.sky_material = ciel
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.6
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC

	# SDFGI : lumière indirecte et reflets en temps réel. Campus plat : la
	# résolution verticale est réduite de moitié au profit de l'horizontale.
	env.sdfgi_use_occlusion = true
	env.sdfgi_read_sky_light = true
	env.sdfgi_bounce_feedback = 0.5
	env.sdfgi_cascades = 4
	env.sdfgi_min_cell_size = 0.2
	env.sdfgi_y_scale = Environment.SDFGI_Y_SCALE_50_PERCENT

	# Brouillard volumétrique léger : de la profondeur sans délaver les couleurs
	# du sens, qui sont le code de lecture de la scène.
	env.volumetric_fog_density = BROUILLARD
	env.volumetric_fog_albedo = Color("#eef0f5")
	env.volumetric_fog_anisotropy = 0.3
	env.volumetric_fog_length = 80.0
	env.volumetric_fog_detail_spread = 2.0
	env.volumetric_fog_gi_inject = 1.0
	env.volumetric_fog_ambient_inject = 0.2
	env.volumetric_fog_sky_affect = 0.0

	# SSAO : ombres de contact sous les pieds et au bas des façades.
	env.ssao_enabled = true
	env.ssao_radius = 0.8
	env.ssao_intensity = 2.5
	env.ssao_power = 1.6
	env.ssao_detail = 0.6
	env.ssao_sharpness = 0.98
	env.ssao_light_affect = 0.15

	# SSIL : la couleur rebondit à courte distance (corps sur le sol, sol sur
	# les façades), en complément du SDFGI qui travaille à plus grande échelle.
	env.ssil_radius = 4.0
	env.ssil_intensity = 1.2
	env.ssil_sharpness = 0.98
	env.ssil_normal_rejection = 1.0

	# Glow : seules les surfaces au-dessus de 1 (rubans, lampes, messages)
	# s'auréolent ; textes et corps restent nets.
	env.glow_enabled = true
	env.glow_intensity = 0.6
	env.glow_bloom = 0.0
	env.glow_hdr_threshold = 1.0
	env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SCREEN
	return env


func regler_qualite(haute: bool) -> void:
	## Haute : SDFGI, SSIL, brouillard volumétrique, ombres douces fines.
	## Légère : SSAO, glow et ombres douces simples seulement, pour une machine
	## qui peine. Le réglage des ombres douces vaut pour toute l'application.
	haute_qualite = haute
	if _env == null:
		return
	_env.sdfgi_enabled = haute
	_env.ssil_enabled = haute
	_env.volumetric_fog_enabled = haute
	_vp.msaa_3d = Viewport.MSAA_4X if haute else Viewport.MSAA_2X
	var douceur: RenderingServer.ShadowQuality = RenderingServer.SHADOW_QUALITY_SOFT_HIGH \
		if haute else RenderingServer.SHADOW_QUALITY_SOFT_LOW
	RenderingServer.directional_soft_shadow_filter_set_quality(douceur)
	RenderingServer.positional_soft_shadow_filter_set_quality(douceur)


# ------------------------------------------------------------------ outils


func _matiere(c: Color, rugosite := 0.8, metal := 0.0) -> StandardMaterial3D:
	## Matériau PBR d'une surface du décor ou d'un corps.
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = rugosite
	m.metallic = metal
	if c.a < 1.0:
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	return m


func _lumineuse(c: Color, energie: float, rugosite := 0.4) -> StandardMaterial3D:
	## Matériau PBR émissif : energie > 1 pour passer le glow et, sur une
	## surface statique, éclairer l'entourage par le SDFGI.
	var m := _matiere(c, rugosite)
	m.emission_enabled = true
	m.emission = Color(c, 1.0)
	m.emission_energy_multiplier = energie
	return m


func _repere(c: Color) -> StandardMaterial3D:
	## Repère d'interface (sélection, alerte) : non éclairé, pour garder sa
	## couleur exacte quelle que soit la lumière.
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	if c.a < 1.0:
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	return m


func _sans_ombre_ni_gi(g: GeometryInstance3D) -> void:
	g.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	g.gi_mode = GeometryInstance3D.GI_MODE_DISABLED


func _etiquette(texte: String, taille: int, couleur: Color) -> Label3D:
	var l := Label3D.new()
	l.text = texte
	if police:
		l.font = police
	l.font_size = taille
	l.pixel_size = 0.006
	l.modulate = couleur
	l.outline_size = 10
	l.outline_modulate = Color(1, 1, 1, 0.9)
	l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l.no_depth_test = true
	_sans_ombre_ni_gi(l)
	return l


func _vider(n: Node) -> void:
	for c in n.get_children():
		c.queue_free()


func _placer_camera() -> void:
	var dir := Vector3(sin(_lacet) * cos(_tangage), sin(_tangage), cos(_lacet) * cos(_tangage))
	_camera.look_at_from_position(_cible + dir * _distance, _cible, Vector3.UP)


func _centre_groupe(g: String) -> Vector3:
	var c: Vector2i = plan.get(g, Vector2i(0, 0))
	return Vector3((c.x - 1) * COLONNE, 0, (c.y - 0.5) * RANG)


func _reveiller() -> void:
	## Couleurs et traits à recalculer à la prochaine image.
	_sale = true
	if is_inside_tree() and is_visible_in_tree():
		set_process(true)


func _notification(what: int) -> void:
	if what == NOTIFICATION_VISIBILITY_CHANGED and _vp != null:
		# Plan 2D affiché : la vue 3D ne rend plus rien et ne calcule plus rien.
		if is_visible_in_tree():
			_vp.render_target_update_mode = SubViewport.UPDATE_WHEN_VISIBLE
			_reveiller()
		else:
			_vp.render_target_update_mode = SubViewport.UPDATE_DISABLED
			vider_animations()
			set_process(false)
	elif what == NOTIFICATION_MOUSE_EXIT and survol != "":
		survol = ""
		_reveiller()


# ------------------------------------------------------------------ données


func mettre_a_jour(etat: Dictionary, voisins: Dictionary) -> void:
	## Appelé à chaque message du pont. Reconstruit le décor quand les groupes
	## ou les agents changent (nouveau run), sinon ne change que les couleurs.
	_etat = etat
	_voisins = voisins
	var agents: Array = etat.get("agents", [])
	var ids := []
	for a in agents:
		ids.append("%s@%s" % [a["id"], a.get("groupe", "")])
	var signature := ",".join(PackedStringArray(ids))
	if signature != _signature:
		_signature = signature
		_construire(agents)
	var sig_chemins := str(etat.get("liens", []).size()) + str(etat.get("run", ""))
	if sig_chemins != _signature_chemins:
		_signature_chemins = sig_chemins
		_construire_chemins()
	_reveiller()


func _construire(agents: Array) -> void:
	_vider(_batiments)
	_vider(_agents)
	_comptes.clear()
	_noeuds.clear()
	_places.clear()
	_hors_champ.clear()
	_sauts.clear()
	var par_groupe := {}
	for a in agents:
		var g: String = a.get("groupe", "?")
		if not par_groupe.has(g):
			par_groupe[g] = []
		par_groupe[g].append(a)
	var noms_visibles := agents.size() <= 30
	for g in par_groupe:
		var centre := _centre_groupe(g)
		_batiment(g, centre)
		var liste: Array = par_groupe[g]
		var cols := mini(liste.size(), 6)
		for j in liste.size():
			var col := j % cols
			var rang := j / cols
			var x := (col - (cols - 1) / 2.0) * PAS_AGENT
			var z := BATIMENT.z / 2.0 + 0.9 + rang * PAS_AGENT
			var place := centre + Vector3(x, 0, z)
			_places[liste[j]["id"]] = place
			_agent(liste[j], place, noms_visibles)


func _batiment(g: String, centre: Vector3) -> void:
	## Décor statique (GI_MODE_STATIC, le défaut) : le SDFGI le voxelise, ses
	## fenêtres et sa lampe émissives éclairent le parvis.
	var corps := MeshInstance3D.new()
	var boite := BoxMesh.new()
	boite.size = BATIMENT
	corps.mesh = boite
	corps.position = centre + Vector3(0, BATIMENT.y / 2.0, 0)
	corps.material_override = _matiere(Color("#f4f2f7"), 0.8)
	_batiments.add_child(corps)
	var toit := MeshInstance3D.new()
	var dalle := BoxMesh.new()
	dalle.size = Vector3(BATIMENT.x + 0.3, 0.25, BATIMENT.z + 0.3)
	toit.mesh = dalle
	toit.position = centre + Vector3(0, BATIMENT.y + 0.12, 0)
	toit.material_override = _matiere(Color("#c9c3d8"), 0.45, 0.35)   # zinc
	_batiments.add_child(toit)
	# Une rangée de fenêtres éclairées sur la façade, pour lire l'échelle.
	var vitrage := _lumineuse(Color("#ffe3b3"), EMISSION_FENETRE, 0.08)
	vitrage.albedo_color = Color("#b9c6d8")
	for i in 5:
		var f := MeshInstance3D.new()
		var vitre := BoxMesh.new()
		vitre.size = Vector3(0.8, 0.9, 0.05)
		f.mesh = vitre
		f.position = centre + Vector3((i - 2) * 1.3, BATIMENT.y * 0.6, BATIMENT.z / 2.0 + 0.01)
		f.material_override = vitrage
		_batiments.add_child(f)
	# La lampe du porche : un globe émissif et sa lumière, ombres douces.
	var porche := centre + Vector3(0, BATIMENT.y * 0.85, BATIMENT.z / 2.0 + 0.35)
	var globe := MeshInstance3D.new()
	var boule := SphereMesh.new()
	boule.radius = 0.12
	boule.height = 0.24
	globe.mesh = boule
	globe.position = porche
	globe.material_override = _lumineuse(Color("#ffd8a8"), EMISSION_LAMPE)
	globe.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_batiments.add_child(globe)
	var lampe := OmniLight3D.new()
	lampe.position = porche + Vector3(0, -0.2, 0.15)
	lampe.light_color = Color("#ffd8a8")
	lampe.light_energy = 0.8
	lampe.omni_range = 7.0
	lampe.shadow_enabled = true
	lampe.omni_shadow_mode = OmniLight3D.SHADOW_CUBE
	lampe.light_size = 0.25          # pénombre PCSS : ombres douces
	lampe.shadow_blur = 1.0
	_batiments.add_child(lampe)
	var nom := _etiquette(groupes_lisibles.get(g, g.replace("_", " ")), 64, Color("#24212e"))
	nom.position = centre + Vector3(0, BATIMENT.y + 1.1, 0)
	_batiments.add_child(nom)
	var compte := _etiquette("", 44, Color("#64607a"))
	compte.position = centre + Vector3(0, BATIMENT.y + 0.55, 0)
	_batiments.add_child(compte)
	_comptes[g] = compte


func _agent(a: Dictionary, place: Vector3, nom_visible: bool) -> void:
	var id: String = a["id"]
	var racine := Node3D.new()
	racine.position = place
	_agents.add_child(racine)
	var corps := MeshInstance3D.new()
	var capsule := CapsuleMesh.new()
	capsule.radius = 0.24
	capsule.height = 1.0
	corps.mesh = capsule
	corps.position = Vector3(0, 0.5, 0)
	var mat := _matiere(Color.WHITE, 0.55)
	corps.material_override = mat
	racine.add_child(corps)
	var tete := MeshInstance3D.new()
	var boule := SphereMesh.new()
	boule.radius = 0.17
	boule.height = 0.34
	tete.mesh = boule
	tete.position = Vector3(0, 1.17, 0)
	tete.material_override = _matiere(Color("#f1e3d3"), 0.7)
	racine.add_child(tete)
	# Le ruban : un anneau satiné et lumineux au poignet, de la couleur du
	# sens, s'il le porte.
	var anneau := MeshInstance3D.new()
	var tore := TorusMesh.new()
	tore.inner_radius = 0.25
	tore.outer_radius = 0.33
	anneau.mesh = tore
	anneau.position = Vector3(0, 0.62, 0)
	var mat_anneau := _lumineuse(Color.WHITE, EMISSION_RUBAN, 0.35)
	anneau.material_override = mat_anneau
	racine.add_child(anneau)
	# Un étudiant saute et change de couleur : GI dynamique, il reçoit la
	# lumière indirecte du SDFGI sans y laisser une empreinte périmée.
	for g in [corps, tete, anneau]:
		(g as GeometryInstance3D).gi_mode = GeometryInstance3D.GI_MODE_DYNAMIC
	var alerte := MeshInstance3D.new()
	var cercle := TorusMesh.new()
	cercle.inner_radius = 0.34
	cercle.outer_radius = 0.4
	alerte.mesh = cercle
	alerte.position = Vector3(0, 0.02, 0)
	alerte.material_override = _repere(Color("#c8553d"))
	_sans_ombre_ni_gi(alerte)
	racine.add_child(alerte)
	var prenom := str(a.get("nom", ""))
	if lisible.is_valid():
		prenom = lisible.call(prenom)
	var nom := _etiquette(prenom, 36, Color("#24212e"))
	nom.position = Vector3(0, 1.6, 0)
	nom.visible = nom_visible
	racine.add_child(nom)
	# Hors du champ de la caméra : ni couleur, ni saut, ni test de survol.
	var champ := VisibleOnScreenNotifier3D.new()
	champ.aabb = AABB(Vector3(-0.5, 0.0, -0.5), Vector3(1.0, 1.9, 1.0))
	champ.screen_exited.connect(_sortir_du_champ.bind(id, racine))
	champ.screen_entered.connect(_entrer_dans_le_champ.bind(id, racine))
	racine.add_child(champ)
	_noeuds[id] = {"racine": racine, "corps": corps, "mat": mat, "anneau": anneau,
		"mat_anneau": mat_anneau, "nom": nom, "alerte": alerte, "nom_visible": nom_visible,
		"vu": []}


func _du_run_courant(id: String, racine: Node3D) -> bool:
	## Un notificateur d'un run précédent, en cours de libération, ne doit pas
	## toucher l'étudiant du même identifiant dans le nouveau run.
	return _noeuds.has(id) and _noeuds[id]["racine"] == racine


func _sortir_du_champ(id: String, racine: Node3D) -> void:
	if not _du_run_courant(id, racine):
		return
	_hors_champ[id] = true
	if _sauts.has(id):
		_sauts.erase(id)
		racine.position = _places[id]


func _entrer_dans_le_champ(id: String, racine: Node3D) -> void:
	if not _du_run_courant(id, racine):
		return
	_hors_champ.erase(id)
	_reveiller()   # sa couleur a pu changer pendant qu'il était hors champ


func _construire_chemins() -> void:
	## Un chemin au sol par paire de groupes reliée par des ponts, plus large
	## quand les ponts sont nombreux. Cloisonné : aucun chemin.
	_vider(_chemins)
	var groupe := {}
	for a in _etat.get("agents", []):
		groupe[a["id"]] = a.get("groupe", "?")
	var ponts := {}
	for l in _etat.get("liens", []):
		if l["type"] != "faible" or not (groupe.has(l["a"]) and groupe.has(l["b"])):
			continue
		var paire := [groupe[l["a"]], groupe[l["b"]]]
		paire.sort()
		var cle := "%s|%s" % paire
		ponts[cle] = int(ponts.get(cle, 0)) + 1
	var hauteur_etiquette := {}
	var pave := _matiere(Color("#cfc7ae"), 0.9)
	for cle in ponts:
		var g: PackedStringArray = (cle as String).split("|")
		var a := _centre_groupe(g[0]) + Vector3(0, 0, BATIMENT.z / 2.0 + 1.5)
		var b := _centre_groupe(g[1]) + Vector3(0, 0, BATIMENT.z / 2.0 + 1.5)
		var n := int(ponts[cle])
		var chemin := MeshInstance3D.new()
		var dalle := BoxMesh.new()
		dalle.size = Vector3(0.25 + 0.15 * n, 0.03, a.distance_to(b))
		chemin.mesh = dalle
		chemin.position = (a + b) / 2.0 + Vector3(0, 0.015, 0)
		chemin.rotation.y = atan2(b.x - a.x, b.z - a.z)
		chemin.material_override = pave
		chemin.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		_chemins.add_child(chemin)
		var milieu := (a + b) / 2.0
		var cle_h := "%d,%d" % [roundi(milieu.x), roundi(milieu.z)]
		var h: float = hauteur_etiquette.get(cle_h, 0.6)
		hauteur_etiquette[cle_h] = h + 0.55
		var e := _etiquette("%d pont%s" % [n, "s" if n > 1 else ""], 36, Color("#64607a"))
		e.position = milieu + Vector3(0, h, 0)
		_chemins.add_child(e)


func _colorer() -> void:
	var agents: Array = _etat.get("agents", [])
	var porteurs := {}
	var totaux := {}
	for a in agents:
		var id: String = a["id"]
		var g: String = a.get("groupe", "?")
		totaux[g] = int(totaux.get(g, 0)) + 1
		if a.get("porte", false):
			porteurs[g] = int(porteurs.get(g, 0)) + 1
		if not _noeuds.has(id) or _hors_champ.has(id):
			continue
		var n: Dictionary = _noeuds[id]
		var c: Color = couleurs.get(a.get("categorie", "aucun_sens"), Color.GRAY)
		var porte: bool = a.get("porte", false)
		var corps := c if porte else c.lerp(Color.WHITE, 0.72)
		var estompe: bool = selection != "" and id != selection \
			and not _voisins.get(selection, {}).has(id)
		if estompe:
			corps = corps.lerp(Color("#d8d6de"), 0.6)
		var nom_visible: bool = n["nom_visible"] or id == survol or id == selection
		var vu := [corps, c, porte, a.get("valide", true), estompe, nom_visible]
		if vu == n["vu"]:
			continue   # rien n'a changé : on ne touche pas aux matériaux
		n["vu"] = vu
		(n["mat"] as StandardMaterial3D).albedo_color = corps
		var mat_anneau: StandardMaterial3D = n["mat_anneau"]
		mat_anneau.albedo_color = c.darkened(0.15)
		mat_anneau.emission = c
		mat_anneau.emission_energy_multiplier = EMISSION_RUBAN_ESTOMPE if estompe else EMISSION_RUBAN
		(n["anneau"] as Node3D).visible = porte
		(n["alerte"] as Node3D).visible = not a.get("valide", true)
		var nom: Label3D = n["nom"]
		nom.visible = nom_visible
		nom.modulate = Color("#24212e") if not estompe else Color("#9a97a6")
	for g in totaux:
		if _comptes.has(g):
			(_comptes[g] as Label3D).text = "%d/%d portent" % [int(porteurs.get(g, 0)), int(totaux[g])]
	if selection != "" and _places.has(selection):
		_anneau_selection.position = _places[selection] + Vector3(0, 0.03, 0)
		_anneau_selection.visible = true
	else:
		_anneau_selection.visible = false


# ------------------------------------------------------------------ animations


func animer_message(de: String, vers: String, couleur: Color) -> void:
	## Un message privé file d'une tête à l'autre ; sans destinataire, une
	## publication publique part en onde au pied de l'auteur. Rien n'est créé
	## pour un effet entièrement hors champ, ni quand la vue est cachée.
	if not _places.has(de) or not is_visible_in_tree():
		return
	if vers != "" and _places.has(vers):
		if _hors_champ.has(de) and _hors_champ.has(vers):
			return
		var bille := MeshInstance3D.new()
		var s := SphereMesh.new()
		s.radius = 0.13
		s.height = 0.26
		bille.mesh = s
		bille.material_override = _lumineuse(couleur, EMISSION_BILLE)
		_sans_ombre_ni_gi(bille)
		_effets.add_child(bille)
		_vols.append({"de": de, "vers": vers, "reste": DUREE_VOL, "noeud": bille})
	else:
		if _hors_champ.has(de):
			return
		var onde := MeshInstance3D.new()
		var t := TorusMesh.new()
		t.inner_radius = 0.9
		t.outer_radius = 1.0
		onde.mesh = t
		var m := _lumineuse(Color(couleur, 0.8), EMISSION_ONDE)
		onde.material_override = m
		_sans_ombre_ni_gi(onde)
		onde.position = _places[de] + Vector3(0, 0.05, 0)
		_effets.add_child(onde)
		_ondes.append({"noeud": onde, "mat": m, "reste": DUREE_ONDE})
	set_process(true)


func eclater(id: String) -> void:
	## Un étudiant qui change de choix ou de sens fait un petit saut, s'il est
	## dans le champ de la caméra.
	if _noeuds.has(id) and not _hors_champ.has(id) and is_visible_in_tree():
		_sauts[id] = DUREE_SAUT
		set_process(true)


func vider_animations() -> void:
	for v in _vols:
		(v["noeud"] as Node).queue_free()
	for o in _ondes:
		(o["noeud"] as Node).queue_free()
	_vols.clear()
	_ondes.clear()
	for id in _sauts:
		if _noeuds.has(id):
			(_noeuds[id]["racine"] as Node3D).position = _places[id]
	_sauts.clear()


func _process(delta: float) -> void:
	_animer(delta)
	if _sale:
		_sale = false
		_colorer()
		_dessiner_traits()
	if _vols.is_empty() and _ondes.is_empty() and _sauts.is_empty():
		set_process(false)   # plus rien ne bouge : la vue dort jusqu'au prochain changement


func _animer(delta: float) -> void:
	for v in _vols:
		v["reste"] -= delta
		var avance: float = 1.0 - float(v["reste"]) / DUREE_VOL
		var a: Vector3 = _places.get(v["de"], Vector3.ZERO) + Vector3(0, 1.3, 0)
		var b: Vector3 = _places.get(v["vers"], Vector3.ZERO) + Vector3(0, 1.3, 0)
		(v["noeud"] as Node3D).position = a.lerp(b, avance) + Vector3(0, sin(avance * PI) * 2.0, 0)
	for v in _vols.filter(func(x): return x["reste"] <= 0.0):
		(v["noeud"] as Node).queue_free()
	_vols = _vols.filter(func(x): return x["reste"] > 0.0)
	for o in _ondes:
		o["reste"] -= delta
		var avance: float = 1.0 - float(o["reste"]) / DUREE_ONDE
		var e := 0.4 + avance * 4.0
		(o["noeud"] as Node3D).scale = Vector3(e, 1.0, e)
		var m: StandardMaterial3D = o["mat"]
		m.albedo_color.a = 0.8 * (1.0 - avance)
		m.emission_energy_multiplier = EMISSION_ONDE * (1.0 - avance)
	for o in _ondes.filter(func(x): return x["reste"] <= 0.0):
		(o["noeud"] as Node).queue_free()
	_ondes = _ondes.filter(func(x): return x["reste"] > 0.0)
	# Seuls les étudiants qui sautent bougent ; les autres restent posés.
	for id in _sauts.keys():
		var racine: Node3D = _noeuds[id]["racine"]
		_sauts[id] -= delta
		if _sauts[id] <= 0.0:
			_sauts.erase(id)
			racine.position = _places[id]
		else:
			var avance: float = 1.0 - float(_sauts[id]) / DUREE_SAUT
			racine.position = _places[id] + Vector3(0, sin(avance * PI) * 0.45, 0)


func _dessiner_traits() -> void:
	## Les regards du jour, ou le réseau (touche L), entre les têtes. Les
	## traits partent des places et non des corps : un saut ne les redessine pas.
	_trait_mesh.clear_surfaces()
	var segments := []
	var categorie := {}
	for a in _etat.get("agents", []):
		categorie[a["id"]] = a.get("categorie", "aucun_sens")
	var gris := Color("#64607a")
	if voir_reseau:
		for l in _etat.get("liens", []):
			var lui: bool = selection != "" and (l["a"] == selection or l["b"] == selection)
			var alpha := 0.55 if l["type"] == "fort" else 0.25
			if selection != "":
				alpha = 0.9 if lui else alpha * 0.25
			segments.append([l["a"], l["b"], Color(gris, alpha)])
	else:
		for r in _etat.get("regards", []):
			var porte: bool = r[3]
			var c: Color = couleurs.get(categorie.get(r[1], ""), gris) if porte else gris
			var alpha := 0.6 if porte else 0.18
			if selection != "":
				alpha = 0.95 if r[0] == selection else alpha * 0.25
			segments.append([r[0], r[1], Color(c, alpha)])
	var dessines := 0
	var hauteur := Vector3(0, HAUTEUR_TRAIT, 0)
	for s in segments:
		if not (_places.has(s[0]) and _places.has(s[1])):
			continue
		if dessines == 0:
			_trait_mesh.surface_begin(Mesh.PRIMITIVE_LINES, _trait_mat)
		_trait_mesh.surface_set_color(s[2])
		_trait_mesh.surface_add_vertex(_places[s[0]] + hauteur)
		_trait_mesh.surface_set_color(s[2])
		_trait_mesh.surface_add_vertex(_places[s[1]] + hauteur)
		dessines += 1
	if dessines > 0:
		_trait_mesh.surface_end()


# ------------------------------------------------------------------ souris


func _agent_sous(p: Vector2) -> String:
	## L'étudiant le plus proche du pointeur, à l'écran, à moins de 22 pixels.
	var meilleur := ""
	var d_min := 22.0
	for id in _noeuds:
		if _hors_champ.has(id):
			continue
		var tete: Vector3 = (_noeuds[id]["racine"] as Node3D).position + Vector3(0, 0.8, 0)
		if _camera.is_position_behind(tete):
			continue
		var d := _camera.unproject_position(tete).distance_to(p)
		if d < d_min:
			d_min = d
			meilleur = id
	return meilleur


func _survoler(p: Vector2) -> void:
	## Le survol se calcule quand la souris ou la caméra bouge, pas à chaque image.
	var id := _agent_sous(p)
	if id != survol:
		survol = id
		_reveiller()


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var b := event as InputEventMouseButton
		if b.button_index == MOUSE_BUTTON_WHEEL_UP and b.pressed:
			_distance = clampf(_distance * 0.9, 10.0, 60.0)
			_placer_camera()
			_survoler(b.position)
		elif b.button_index == MOUSE_BUTTON_WHEEL_DOWN and b.pressed:
			_distance = clampf(_distance * 1.1, 10.0, 60.0)
			_placer_camera()
			_survoler(b.position)
		elif b.button_index == MOUSE_BUTTON_LEFT:
			if b.pressed:
				_glisse = false
				_depart_clic = b.position
			elif not _glisse:
				agent_clique.emit(_agent_sous(b.position))
		accept_event()
	elif event is InputEventMouseMotion:
		var m := event as InputEventMouseMotion
		if m.button_mask & MOUSE_BUTTON_MASK_LEFT:
			if m.position.distance_to(_depart_clic) > 4.0:
				_glisse = true
			_lacet -= m.relative.x * 0.008
			_tangage = clampf(_tangage + m.relative.y * 0.006, deg_to_rad(15.0), deg_to_rad(85.0))
			_placer_camera()
			accept_event()
		_survoler(m.position)
