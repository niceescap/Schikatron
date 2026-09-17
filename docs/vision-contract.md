# Contrat expérimental de vision — 0.1.0

Statut : proposition implémentée pour validation, pas un standard biomécanique validé.
Aucune KB, aucun prompt d'extraction scientifique et aucun schema.json scientifique ne sont modifiés.

## Périmètre

Une vue latérale fixe, vélo entier visible, cycliste pédalant vers l'avant. Les sorties sont des **projections 2D**, jamais des angles articulaires 3D certifiés. L'empattement est une référence provisoire. Il supprime l'échelle globale, pas la perspective, la distorsion optique ou la parallaxe entre les deux côtés du corps. Un contrôle par ellipses de roues ne constitue pas une calibration complète.

Le prototype ne détecte pas l'anatomie sans marqueur. Il reçoit des points annotés ou les centroïdes de marqueurs colorés configurés. Le placement d'un marqueur sur la peau ou la chaussure est un proxy, pas une mesure directe du centre articulaire. Les mesures demandent une validation humaine du placement.

## Landmarks

Obligatoires pour sélectionner un cycle : `rear_hub`, `front_hub`, `bb_center`, `pedal_spindle_left` OU `pedal_spindle_right` selon le côté de référence déclaré. `pedal_spindle` désigne la projection de l'axe de pédale, pas l'axe de pédalier.

Optionnels, séparés par côté anatomique réel (`left_` / `right_`, jamais déduits du côté de l'image) : `hip`, `knee`, `ankle`, `forefoot`, `heel`, `shoulder`, `elbow`, `wrist`.

Les annotations doivent préciser dans `landmark_definitions` leurs repères anatomiques/proxies : hanche (p. ex. marqueur du grand trochanter, pas centre de hanche), genou (repère latéral défini), cheville (malléole définie), avant-pied (repère métatarsien ou chaussure défini), talon (repère de chaussure défini), épaule, coude, poignet. Aucun repère caché sous la chaussure n'est considéré directement visible.

Optionnels vélo : `saddle_nose`, `saddle_rear`, `handlebar_reference`, `hand_contact_left`, `hand_contact_right`, deuxième axe de pédale. Les points de selle définissent une corde géométrique, pas nécessairement le plan de support de la selle. La référence de cintre et le contact de main sont distincts. Un corps de pédale nécessite plusieurs points pour en mesurer l'orientation : hors MVP.

## Repère

Entrée : pixels, X vers la droite, Y vers le bas. Origine = moyeu arrière ; X = direction arrière → avant. Y = perpendiculaire dont la composante verticale image pointe vers le haut (images latérales non tournées). Coordonnées : produit scalaire avec chaque axe, divisé par la distance entre moyeux, multiplié par 100. Avant = (100, 0). Toutes les distances, dx et dy sont en pourcentage de l'empattement projeté. Les observations pixels sont conservées dans chaque état sélectionné.

## Phase et temps

Un côté de référence doit être déclaré. Pour ce côté : 0° = manivelle vers +Y ; 90° = vers +X (avant du vélo) ; 180° = vers -Y ; 270° = vers -X. La phase est `atan2(dx, dy) modulo 360`, relative au centre du pédalier. PMH/PMB sont ici relatifs au repère vélo, pas à une verticale gravitaire mesurée.

On suit le premier tour complet disponible de ce côté : deux passages consécutifs à 0°. Il faut donc filmer plus d'un tour, de préférence au moins trois. Le mouvement doit être vers l'avant, avec moins de 180° entre deux observations valides ; les vidéos sous-échantillonnées peuvent rester ambiguës et doivent être évitées. Un déplacement apparent inverse ou >=180° est rejeté par le MVP plutôt que réparé. Les bornes temporelles des passages à 0° sont interpolées linéairement et étiquetées comme telles ; aucune position corporelle n'est interpolée.

Exactement 12 états à 0, 30, …, 330°, choisis dans ce même tour, sans moyenne inter-tours. Chaque état conserve la phase observée et son erreur par rapport à la cible. La tolérance est configurable (5° par défaut, valeur d'ingénierie provisoire, non validée scientifiquement). Si aucune observation ne convient, état `missing`. 360° n'est pas un treizième état. Les deux côtés présents dans un état correspondent au même instant ; aucune copie controlatérale décalée de 180°.

## Angles

Tous en degrés [0, 180]. Pour A–B–C : angle interne entre B→A et B→C, calculé par produit scalaire borné. Segment nul ou point absent → `value: null`, `status: missing`.

- `knee_internal` : hip–knee–ankle ; jambe alignée = 180°, **ce n'est pas une flexion de genou à zéro en extension**.
- `hip_trunk_thigh_internal` : shoulder–hip–knee ; angle projeté tronc/cuisse, pas flexion anatomique corrigée du bassin.
- `elbow_internal` : shoulder–elbow–wrist.
- `ankle_shank_forefoot_internal` : knee–ankle–forefoot ; dépend du proxy de pied, pas un angle de dorsiflexion clinique.

Les noms, points et conventions accompagnent les nombres. Aucune équivalence automatique avec une publication utilisant d'autres repères.

## Distances

Pour les paires configurées : distance euclidienne, dx et dy signés de A vers B. Par défaut : pédalier→nez de selle, nez de selle→référence cintre, talon→avant-pied de chaque côté. Leur nom n'implique ni hauteur fonctionnelle de selle ni longueur anatomique du pied.

## Qualité et provenance

Valeurs JSON numériques, unités dans des champs séparés ; absence = null, jamais zéro de substitution ou NaN. Une observation contient `xy_px`, `status`, `confidence` (null si non calibrée), et éventuellement `method`/`quality`. `observed` et `estimated` sont distingués ; `missing`/`occluded` n'apportent aucune coordonnée exploitable. Les estimations fournies par un système amont restent étiquetées dans les mesures dérivées. Le score d'un détecteur n'est pas une incertitude angulaire en degrés. Le prototype ne propage pas encore d'incertitude métrologique : `uncertainty_deg: null`.

L'adaptateur couleur ne fabrique pas un score de confiance : il conserve aire du blob et ambiguïté ; plusieurs blobs de la même couleur donnent un point manquant. Les landmarks non configurés sont absents, les calculs dépendants sont manquants. Une sortie géométrique exploitable peut donc ne contenir aucun angle corporel.

## Sortie

`schema_version`, `producer`, `source`, `landmark_definitions`, `reference`, `cycle`, `quality`, `states`. Chaque état : cible, statut, frame/timestamp/phase observés (ou null), observations pixels, coordonnées normalisées, angles par côté, relations de distances. La liste des états a toujours exactement 12 entrées pour une extraction réussie. Une vidéo sans tour complet ou sans repère exploitable provoque une erreur, pas un faux cycle.

Les extrema, amplitudes, asymétries et interprétations sont réservés à la couche d'analyse. Douze échantillons peuvent manquer un extremum réel entre deux états : ne pas les présenter comme extrema continus exacts.

## Validation avant usage

Tests synthétiques : normalisation, miroir latéral, angles, sélection monocycle, état absent, absence de côté caché. Puis vidéos latérales consenties : annotations manuelles répétées, écarts pixels/phase/angles, occlusions, flou, changement de résolution, perspective. Évaluer plusieurs cadences et fréquences d'image ; à 90 tr/min et 30 fps, l'avancée moyenne est 18°/image, donc ±5° ne garantit pas tous les états. Les tests logiciels ne valident pas l'exactitude anatomique.

Pas de vidéo de test utilisateur disponible à la création du prototype. Pas de précision clinique annoncée. Traitement local ; ne pas publier de vidéos personnelles dans ce dépôt public.
