extends SceneTree
## Vérification de l'application réelle (main.tscn) branchée sur pont.py --rejeu.
## La scène se connecte elle-même au pont ; ce script attend la fin du rejeu, puis
## agit comme un utilisateur (H, espace, flèche gauche) et vérifie ce qu'elle affiche.
##   Godot --path godot -s res://verifier_rejeu.gd -- <dossier> <evenements> <adoption_finale>

var echecs := 0
var scene: Node
var dossier := ""


func verifier(nom: String, ok: bool) -> void:
	print(("  ok    " if ok else "  ECHEC ") + nom)
	if not ok:
		echecs += 1


func touche(code: Key) -> void:
	var t := InputEventKey.new()
	t.keycode = code
	t.pressed = true
	scene._unhandled_input(t)


func attendre(condition: Callable, secondes: float) -> bool:
	var fin := Time.get_ticks_msec() + int(secondes * 1000)
	while Time.get_ticks_msec() < fin:
		if condition.call():
			return true
		await process_frame
	return condition.call()


func image(nom: String) -> void:
	if dossier == "" or DisplayServer.get_name() == "headless":
		return
	for i in 4:
		await process_frame
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(dossier)
	root.get_texture().get_image().save_png(dossier.path_join(nom))
	print("  image  " + nom)


func compte(canal: String) -> int:
	var n := 0
	for x in scene.narrations:
		n += x.get(canal, []).size()
	return n


func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	dossier = a[0]
	var attendus := int(a[1])
	var adoption := float(a[2])
	scene = load("res://main.tscn").instantiate()
	root.add_child(scene)
	verifier("l'application démarre et se connecte au pont",
		await attendre(func(): return scene.connecte, 20.0))
	verifier("tous les événements du rejeu sont reçus (%d)" % attendus,
		await attendre(func(): return int(scene.etat.get("indicateurs", {}).get("evenements_vus", 0)) == attendus, 240.0))
	await attendre(func(): return false, 3.0)   # les dernières narrations suivent le dernier relevé
	var ind: Dictionary = scene.etat.get("indicateurs", {})
	verifier("adoption affichée = dernier relevé du journal (%.2f)" % adoption,
		absf(float(ind.get("taux_adoption", -1.0)) - adoption) < 1e-6)
	verifier("des narrations sont affichées (%d), avec %d constats" % [scene.narrations.size(), compte("constats")],
		scene.narrations.size() > 0 and compte("constats") > 0)
	verifier("des hypothèses sont reçues (%d) mais masquées par défaut" % compte("hypotheses"),
		compte("hypotheses") > 0 and not scene.voir_hypotheses and scene.vue_recit)
	await image("rejeu_fin_hypotheses_masquees.png")
	touche(KEY_H)
	verifier("H : hypothèses affichées, à part", scene.voir_hypotheses)
	await image("rejeu_fin_hypotheses_affichees.png")
	touche(KEY_H)
	verifier("H : hypothèses de nouveau masquées", not scene.voir_hypotheses)
	# Commandes du rejeu, comme un utilisateur.
	var jour: int = scene._jour()
	var narrations_avant: int = scene.narrations.size()
	scene.bandeau = {"texte": "", "couleur": Color.BLACK, "reste": 0.0}
	touche(KEY_SPACE)
	verifier("espace : le pont accuse la commande de lecture (bandeau « rejeu : … »)",
		await attendre(func(): return str(scene.bandeau["texte"]).begins_with("rejeu"), 10.0))
	print("         bandeau : " + str(scene.bandeau["texte"]))
	touche(KEY_LEFT)
	verifier("flèche gauche : retour au jour %d" % (jour - 1),
		await attendre(func(): return scene._jour() == jour - 1, 20.0))
	await attendre(func(): return false, 1.0)
	# La scène garde au plus 12 narrations : le critère est qu'aucune ne soit postérieure
	# au jour où l'on est revenu, pas qu'il y en ait moins.
	var limite: int = (jour - 1) * 1440
	var plus_tard := 0
	var t_max := 0
	for x in scene.narrations:
		t_max = maxi(t_max, int(x.get("t_sim", 0)))
		if int(x.get("t_sim", 0)) > limite:
			plus_tard += 1
	verifier("au jour précédent : moins d'événements vus (%d), %d narrations affichées, aucune après J%d (la plus récente : J%d)"
		% [int(scene.etat.get("indicateurs", {}).get("evenements_vus", 0)), scene.narrations.size(),
			jour - 1, t_max / 1440],
		int(scene.etat.get("indicateurs", {}).get("evenements_vus", 0)) < attendus and plus_tard == 0
		and narrations_avant > 0)
	await image("rejeu_jour_precedent.png")
	print("Toutes les verifications passent." if echecs == 0 else "%d echec(s)" % echecs)
	quit(1 if echecs else 0)
