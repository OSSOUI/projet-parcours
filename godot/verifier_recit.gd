extends SceneTree
## Banc de test de l'affichage du récit, dans le vrai moteur et avec la vraie scène.
## Aucun pont, aucun modèle : les messages sont ceux que le pont enverrait.
##   Godot --path godot -s res://verifier_recit.gd -- <dossier_sortie>
## Avec fenêtre, il enregistre aussi deux images : hypothèses masquées, puis affichées (H).

var echecs := 0


func verifier(nom: String, ok: bool) -> void:
	print(("  ok    " if ok else "  ECHEC ") + nom)
	if not ok:
		echecs += 1


func _initialize() -> void:
	var sortie: String = OS.get_cmdline_user_args()[0] if OS.get_cmdline_user_args().size() > 0 else ""
	var scene: Node = load("res://main.tscn").instantiate()
	root.add_child(scene)
	await process_frame
	scene.ws.close()   # pas de pont : on parle à la scène directement
	var etat := {"type": "etat", "run": "banc_recit", "modele_social": "v1", "jours": 4,
		"agents": [], "historique": [], "fil": [], "liens": [], "injections": [],
		"regards": [], "sens_groupes": [], "contre_tendances": [],
		"indicateurs": {"t_sim": 5760, "t_sim_lisible": "J05 00:00", "taux_adoption": 0.65,
			"sens_dominant": "suivre_la_foule", "part_sens_dominant": 0.55, "evenements_vus": 293},
		"narrations": []}
	scene._recevoir(JSON.stringify(etat))
	var n := {"narration": "N4", "statut": "partiel", "t_sim": 5760, "t_sim_lisible": "J05 00:00",
		"fenetre": {"debut": "J04 00:00", "fin": "J05 00:00"},
		"constats": [{"texte": "CONSTAT_VERIFIE adoption 65 %", "sources": ["banc#1"]}],
		"hypotheses": [{"texte": "HYPOTHESE_MASQUEE le ruban serait devenu un code", "sources": ["F1"]}],
		"incertitudes": [{"texte": "INCERTITUDE_MASQUEE rien ne tranche encore", "sources": ["F1"]}],
		"rejetees": 2}
	scene._recevoir(JSON.stringify({"type": "narration", "narration": n}))
	verifier("la narration est reçue par la scène", scene.narrations.size() == 1)
	verifier("le récit est la vue par défaut", scene.vue_recit)
	verifier("hypothèses et incertitudes masquées par défaut", not scene.voir_hypotheses)
	verifier("les canaux restent séparés dans la scène",
		scene.narrations[0]["constats"].size() == 1 and scene.narrations[0]["hypotheses"].size() == 1
		and scene.narrations[0]["incertitudes"].size() == 1)
	await _image(sortie, "recit_hypotheses_masquees.png")
	var touche := InputEventKey.new()
	touche.keycode = KEY_H
	touche.pressed = true
	scene._unhandled_input(touche)
	verifier("H affiche les hypothèses et incertitudes", scene.voir_hypotheses)
	await _image(sortie, "recit_hypotheses_affichees.png")
	scene._unhandled_input(touche)
	verifier("H les masque de nouveau", not scene.voir_hypotheses)
	var touche_n := InputEventKey.new()
	touche_n.keycode = KEY_N
	touche_n.pressed = true
	scene._unhandled_input(touche_n)
	verifier("N passe au réseau interne", not scene.vue_recit)
	# Un nouvel état (reconnexion) garde les narrations qu'il apporte.
	etat["narrations"] = [n]
	scene._recevoir(JSON.stringify(etat))
	verifier("un instantané qui apporte les narrations les remplace", scene.narrations.size() == 1)
	print("Toutes les verifications passent." if echecs == 0 else "%d echec(s)" % echecs)
	quit(1 if echecs else 0)


func _image(dossier: String, nom: String) -> void:
	if dossier == "" or DisplayServer.get_name() == "headless":
		return
	for i in 3:
		await process_frame
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(dossier)
	root.get_texture().get_image().save_png(dossier.path_join(nom))
	print("  image  " + dossier.path_join(nom))
