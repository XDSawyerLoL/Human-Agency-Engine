import crypto from 'node:crypto';

const HOUR = 3600_000;
const DAY_HOURS = 24;
const YEAR_HOURS = 365 * DAY_HOURS;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const sigmoid = x => 1 / (1 + Math.exp(-x));
const logit = p => Math.log(p / (1 - p));
const hash = value => crypto.createHash('sha256').update(value).digest('hex').slice(0, 24);

const S = (id, domain, prior, hours, pattern, headline, summary, known, chain, watch, falsify, tags = [], interest = 0.7, contrary = []) => ({
  id, domain, prior, hours, pattern, headline, summary, known, chain, watch, falsify, tags, interest, contrary
});

const SCENARIOS = {
  major_earthquake: [
    S('quake-aftershocks', 'natural_hazards', .46, [0,72], .86,
      g => `Après le séisme : risque élevé de répliques et de restrictions d’accès autour de ${g}.`,
      g => `Les prochaines heures peuvent concentrer les répliques, inspections et fermetures locales autour de ${g}.`,
      'Un séisme significatif vient d’être détecté.',
      ['séisme significatif','répliques et inspections','fermetures / restrictions','mobilité et services perturbés'],
      ['répliques M5+','fermetures de routes ou aéroports','alertes tsunami ou évacuations'],
      'Aucune réplique significative ni restriction d’accès observable avant la fin de la fenêtre.',
      ['Mobilité','Infrastructures'], .96),
    S('quake-recovery', 'natural_hazards', .34, [72,720], .78,
      g => `Séisme : risque de goulots d’étranglement sur les secours, réseaux et approvisionnements autour de ${g}.`,
      g => `Une crise sismique importante peut déplacer le risque vers les réseaux, le logement et la logistique dans les jours suivants.`,
      'Les dommages et inspections post-séisme peuvent persister après la phase d’urgence.',
      ['dommages initiaux','réseaux contraints','besoins de secours et relogement','tensions locales sur logistique et services'],
      ['coupures prolongées','besoins de relogement','restriction d’accès persistante'],
      'Les réseaux et accès reviennent rapidement à la normale sans tension logistique notable.',
      ['Secours','Logistique','Réseaux'], .82),
    S('quake-reconstruction', 'economy_labor', .24, [720,4320], .67,
      g => `Après le séisme : probabilité d’une hausse des dépenses de reconstruction et des tensions locales sur le bâtiment autour de ${g}.`,
      g => `Si les dommages sont confirmés, la reconstruction peut déplacer la demande vers matériaux, assurances et main-d’œuvre sur plusieurs mois.`,
      'Les dommages sismiques significatifs déclenchent souvent une phase de réparation plus longue que l’urgence initiale.',
      ['dommages confirmés','indemnisations et budgets publics','demande de matériaux et travaux','reconstruction locale'],
      ['estimations de dommages en hausse','plans publics de reconstruction','hausse des demandes d’indemnisation'],
      'Les évaluations concluent à des dommages limités et aucun programme de reconstruction significatif n’est engagé.',
      ['Bâtiment','Assurance','Emploi'], .66)
  ],
  geomagnetic_storm_watch: [
    S('space-gnss', 'cyber_technology', .32, [0,48], .80,
      () => 'Météo spatiale : risque accru de perturbations GNSS, radio HF et services satellitaires.',
      () => 'Le pic géomagnétique attendu peut perturber brièvement navigation, radio et certains services dépendants des satellites.',
      'NOAA projette une activité géomagnétique élevée.',
      ['activité géomagnétique élevée','ionosphère perturbée','erreurs GNSS / radio HF','services ponctuellement dégradés'],
      ['Kp ≥ 6','alertes NOAA G2+','rapports d’erreurs GNSS ou radio'],
      'Le pic géomagnétique reste inférieur au niveau prévu ou aucune perturbation technique n’est rapportée.',
      ['Satellites','Navigation'], .86),
    S('space-operations', 'cyber_technology', .22, [24,168], .64,
      () => 'Opérateurs satellites : probabilité accrue de mesures de protection et d’ajustements opérationnels.',
      () => 'Si l’activité solaire se confirme, les opérateurs les plus exposés peuvent modifier temporairement leurs opérations.',
      'Une activité géomagnétique forte augmente le risque opérationnel pour certains systèmes spatiaux.',
      ['activité solaire forte','risque sur satellites','mesures de protection','opérations adaptées'],
      ['bulletins opérateurs','changements de mode satellite','alertes de radiation'],
      'Aucune mesure opérationnelle ni anomalie n’est observée pendant l’épisode.',
      ['Espace','Télécoms'], .58)
  ],
  disease_outbreak_signal: [
    S('health-surveillance', 'public_health', .40, [48,336], .76,
      g => `Santé : probable intensification de la surveillance autour de ${g}.`,
      g => `Le signal officiel peut entraîner davantage de tests, d’investigations et de recommandations locales dans les prochains jours.`,
      'L’OMS publie un signal officiel de foyer ou d’événement sanitaire.',
      ['signal sanitaire officiel','investigation renforcée','détection de cas supplémentaires','adaptation des recommandations'],
      ['nouveaux cas confirmés','extension géographique','recommandations sanitaires renforcées'],
      'Le foyer reste contenu sans nouveaux cas ni renforcement de la surveillance pendant deux semaines.',
      ['Santé','Surveillance'], .86),
    S('health-local-pressure', 'public_health', .30, [168,1440], .70,
      g => `Santé : risque de pression locale sur les soins et les comportements de prévention autour de ${g}.`,
      g => `Si la transmission progresse, la pression peut se déplacer vers les consultations, la prévention et certains déplacements.`,
      'La poursuite d’un foyer peut produire des effets comportementaux avant une crise sanitaire large.',
      ['cas persistants','hausse de vigilance','demande de soins / prévention','adaptation locale des comportements'],
      ['hausse des hospitalisations','mesures locales','extension des cas'],
      'La transmission ralentit et les indicateurs sanitaires se normalisent dans les deux mois.',
      ['Soins','Prévention','Mobilité'], .73),
    S('health-medium-response', 'public_health', .18, [1440,8760], .58,
      g => `Santé : possibilité d’un programme durable de contrôle, vaccination ou recherche si le foyer persiste autour de ${g}.`,
      g => `Un foyer qui ne s’éteint pas peut déclencher une réponse sanitaire plus durable sur plusieurs mois.`,
      'Un signal OMS isolé ne suffit pas ; ce scénario dépend d’une persistance mesurable du foyer.',
      ['foyer persistant','réponse sanitaire prolongée','financement / recherche ciblée','programme de contrôle durable'],
      ['transmission persistante','financements spécifiques','campagnes ciblées'],
      'Le foyer s’éteint sans programme durable de contrôle, recherche ou vaccination dans l’année.',
      ['Recherche','Vaccination'], .48)
  ],
  wildfire_emergency: [
    S('fire-air-mobility', 'natural_hazards', .48, [0,96], .84,
      g => `Incendies : risque d’aggravation de la qualité de l’air et de perturbations de mobilité près de ${g}.`,
      g => `Fumées, propagation et évacuations peuvent rapidement toucher la mobilité et la qualité de l’air.`,
      'Un incendie actif est signalé par une source d’observation terrestre.',
      ['incendie actif','fumées / propagation','air et visibilité dégradés','évacuations ou transports perturbés'],
      ['extension du périmètre','alertes qualité de l’air','évacuations / fermetures'],
      'Le feu est contenu sans extension, évacuation ni dégradation notable de l’air.',
      ['Air','Mobilité','Secours'], .94),
    S('fire-economic-aftershock', 'economy_labor', .32, [168,1440], .71,
      g => `Incendies : risque de pertes touristiques, agricoles ou assurantielles autour de ${g} dans les prochaines semaines.`,
      g => `Une saison de feu active peut déplacer les conséquences vers l’économie locale après l’urgence.`,
      'L’impact économique apparaît souvent après la phase immédiate d’évacuation et de lutte.',
      ['incendie prolongé','dommages / accès limités','activité locale perturbée','pertes et indemnisations'],
      ['zones brûlées en hausse','fermetures touristiques','déclarations de sinistres'],
      'L’incendie reste limité et aucune perte économique notable n’est documentée dans les deux mois.',
      ['Tourisme','Agriculture','Assurance'], .72),
    S('fire-adaptation', 'regulation_policy', .20, [2160,17520], .61,
      g => `Après les incendies : probabilité d’investissements supplémentaires en prévention et adaptation autour de ${g}.`,
      g => `Des dégâts répétés peuvent faire basculer les décisions publiques vers la prévention, la forêt et la résilience sur un à deux ans.`,
      'Les épisodes sévères peuvent modifier durablement les budgets de prévention lorsque les dommages sont répétés.',
      ['dommages répétés','pression assurantielle et publique','budgets de prévention','adaptation durable'],
      ['nouveaux budgets anti-incendie','règles d’urbanisme','programmes de débroussaillement'],
      'Aucun renforcement significatif des politiques ou investissements de prévention n’apparaît dans les deux ans.',
      ['Prévention','Forêt','Résilience'], .50)
  ],
  flood_emergency: [
    S('flood-access', 'natural_hazards', .50, [0,96], .86,
      g => `Inondations : risque de coupures d’accès et de tensions logistiques autour de ${g}.`,
      g => `Les routes, réseaux et accès locaux sont les premières conséquences à surveiller dans les prochaines heures.`,
      'Une inondation active ou une activation d’urgence est détectée.',
      ['crue / inondation','routes et réseaux exposés','accès restreints','retards logistiques et services perturbés'],
      ['routes coupées','évacuations','ruptures locales de réseau'],
      'Les niveaux baissent sans coupure d’accès ni perturbation logistique notable.',
      ['Transport','Réseaux','Secours'], .95),
    S('flood-local-prices', 'supply_fuel', .32, [72,1008], .70,
      g => `Inondations : risque de tensions temporaires sur certains approvisionnements et prix locaux autour de ${g}.`,
      g => `Si les accès restent perturbés, certains biens, matériaux ou services peuvent devenir temporairement plus rares.`,
      'Une perturbation d’accès prolongée peut se transmettre aux chaînes logistiques locales.',
      ['accès perturbés','livraisons retardées','stocks locaux sous pression','hausse temporaire de coûts'],
      ['retards de livraison','fermetures d’entrepôts','tensions sur certains prix'],
      'Les chaînes logistiques se normalisent sans pénurie ni hausse de coûts notable.',
      ['Approvisionnement','Prix'], .70),
    S('flood-rebuild', 'economy_labor', .26, [720,8760], .66,
      g => `Après les inondations : hausse probable des besoins de réparation, d’assurance et de travaux autour de ${g}.`,
      g => `Les dégâts confirmés peuvent entretenir pendant des mois la demande de réparation et de reconstruction.`,
      'Les dommages hydrologiques peuvent créer une seconde vague économique après la décrue.',
      ['dommages confirmés','sinistres assurés','besoins de réparation','activité de reconstruction'],
      ['déclarations de catastrophe','estimations de dommages','marchés de travaux publics'],
      'Les dommages restent limités et aucune hausse significative des travaux ou indemnisations n’apparaît dans l’année.',
      ['Bâtiment','Assurance','Travaux'], .64)
  ],
  severe_storm_emergency: [
    S('storm-power-transport', 'weather_climate', .47, [0,72], .82,
      g => `Tempête : risque de perturbations de transport et d’électricité autour de ${g}.`,
      g => `Les prochaines heures concentrent le risque de coupures, retards et annulations.`,
      'Une tempête sévère active est suivie par les observateurs mondiaux.',
      ['tempête sévère','vents / pluies extrêmes','infrastructures exposées','retards et coupures'],
      ['rafales extrêmes','annulations de transport','coupures électriques'],
      'La tempête faiblit sans perturbation significative des transports ou de l’électricité.',
      ['Transport','Électricité'], .94),
    S('storm-supply-insurance', 'supply_fuel', .31, [72,720], .68,
      g => `Tempête : risque de retards logistiques et de hausse des sinistres autour de ${g} dans les jours suivants.`,
      g => `Après la tempête, la pression peut se déplacer vers les livraisons, les assurances et la remise en service.`,
      'Les perturbations de réseau peuvent continuer après le passage du phénomène météo.',
      ['dommages / coupures','retards de remise en service','livraisons décalées','sinistres et coûts locaux'],
      ['retards persistants','demandes d’indemnisation','fermetures prolongées'],
      'Les réseaux reviennent rapidement à la normale sans impact logistique ou assurantiel notable.',
      ['Logistique','Assurance'], .70),
    S('storm-resilience', 'regulation_policy', .21, [720,4320], .60,
      g => `Après la tempête : probabilité d’investissements de résilience supplémentaires autour de ${g}.`,
      g => `Des dommages importants peuvent accélérer les décisions sur réseaux, digues, électricité ou normes de construction.`,
      'Les épisodes sévères servent souvent de déclencheur à des investissements déjà envisagés.',
      ['dommages confirmés','vulnérabilités révélées','arbitrages budgétaires','investissements de résilience'],
      ['plans de reconstruction','nouveaux budgets réseau','révisions de normes'],
      'Aucun investissement ou changement de politique notable n’est engagé dans les six mois.',
      ['Résilience','Infrastructures'], .52)
  ],
  volcanic_emergency: [
    S('volcano-airspace', 'natural_hazards', .40, [0,168], .78,
      g => `Volcan : risque accru de restrictions aériennes et d’exposition aux cendres près de ${g}.`,
      g => `Cendres et gaz peuvent rapidement affecter l’aviation et les zones proches.`,
      'Une activité volcanique active est détectée.',
      ['activité volcanique','cendres / gaz','zones aériennes et populations exposées','restrictions ou déroutements'],
      ['VAAC / NOTAM','panache de cendres','évacuations'],
      'Aucun panache significatif, restriction aérienne ou évacuation n’apparaît dans la semaine.',
      ['Aviation','Santé'], .86),
    S('volcano-local-economy', 'economy_labor', .27, [168,1440], .64,
      g => `Volcan : risque de baisse touristique et de perturbations agricoles ou logistiques autour de ${g}.`,
      g => `Si l’activité persiste, les conséquences peuvent migrer vers tourisme, agriculture et fret local.`,
      'La persistance volcanique peut prolonger les effets bien au-delà des premières restrictions.',
      ['activité persistante','cendres / accès contraints','activité économique réduite','pertes locales'],
      ['annulations touristiques','dommages agricoles','restrictions prolongées'],
      'L’activité retombe sans impact économique documenté dans les deux mois.',
      ['Tourisme','Agriculture'], .62)
  ],
  drought_emergency: [
    S('drought-water', 'weather_climate', .38, [168,2160], .74,
      g => `Sécheresse : risque de restrictions d’eau et de tension sur les réserves autour de ${g}.`,
      g => `Si le déficit persiste, la prochaine étape probable est un durcissement de la gestion de l’eau.`,
      'Un épisode de sécheresse persistant est suivi par les observateurs.',
      ['déficit hydrique','réserves sous pression','restrictions graduelles','arbitrages sur les usages'],
      ['restrictions d’eau','baisse des réserves','alertes agricoles'],
      'Les réserves se normalisent sans restriction significative dans les trois mois.',
      ['Eau','Agriculture'], .82),
    S('drought-food', 'supply_fuel', .33, [720,4320], .70,
      g => `Sécheresse : risque de révisions de récolte et de pression sur certains prix alimentaires autour de ${g}.`,
      g => `Le déficit hydrique peut se transmettre aux rendements puis aux prix sur plusieurs mois.`,
      'Le risque agricole augmente lorsque la sécheresse recouvre une période critique des cultures.',
      ['déficit hydrique','rendements révisés','offre agricole réduite','pression sur certains prix'],
      ['révisions de récolte','hausse des prix agricoles','restrictions d’irrigation'],
      'Les rendements restent proches des attentes et aucune pression de prix liée à la sécheresse n’apparaît dans six mois.',
      ['Alimentation','Agriculture','Prix'], .76),
    S('drought-adaptation', 'regulation_policy', .22, [4320,26280], .62,
      g => `À plus long terme : probabilité d’investissements supplémentaires dans l’eau et l’adaptation autour de ${g}.`,
      g => `Si les épisodes se répètent, la pression peut déplacer les investissements vers stockage, irrigation et sobriété sur un à trois ans.`,
      'Une sécheresse ponctuelle ne suffit pas : ce scénario dépend de la persistance ou de la répétition du stress hydrique.',
      ['stress hydrique répété','coûts économiques visibles','arbitrages publics','investissements d’adaptation'],
      ['plans eau','investissements irrigation / stockage','nouvelles restrictions structurelles'],
      'Aucun investissement ou changement durable de politique de l’eau n’apparaît dans les trois ans.',
      ['Eau','Adaptation','Investissement'], .58)
  ],
  landslide_emergency: [
    S('landslide-access', 'natural_hazards', .43, [0,168], .78,
      g => `Glissement de terrain : risque de coupures routières et d’accès difficiles autour de ${g}.`,
      g => `Routes, secours et réseaux locaux peuvent être perturbés pendant plusieurs jours.`,
      'Un glissement de terrain actif est signalé.',
      ['terrain instable','axes exposés','accès interrompus','secours et mobilité contraints'],
      ['routes coupées','évacuations','nouveaux mouvements de terrain'],
      'Aucune coupure d’axe ni évacuation significative n’est observée dans la semaine.',
      ['Routes','Secours'], .80),
    S('landslide-recovery', 'economy_labor', .28, [168,1440], .64,
      g => `Glissement de terrain : probabilité de travaux de sécurisation et de réparation autour de ${g}.`,
      g => `Après l’urgence, la remise en état des axes et talus peut soutenir des travaux sur plusieurs semaines.`,
      'Les dégâts géotechniques nécessitent souvent une phase de sécurisation distincte de l’urgence.',
      ['dommages confirmés','diagnostic géotechnique','travaux de sécurisation','réouverture progressive'],
      ['marchés de travaux','fermetures prolongées','estimations de dommages'],
      'Les accès sont rétablis sans travaux significatifs dans les deux mois.',
      ['Travaux','Infrastructures'], .60)
  ],
  cryosphere_disruption: [
    S('ice-navigation', 'transport_mobility', .28, [168,2160], .60,
      g => `Cryosphère : risque de perturbations saisonnières de navigation ou d’accès autour de ${g}.`,
      g => `Une anomalie de glace ou de neige peut modifier temporairement certains itinéraires et accès.`,
      'Une anomalie active de glace ou de cryosphère est suivie par NASA EONET.',
      ['anomalie cryosphérique','accès ou routes saisonnières affectés','itinéraires adaptés','retards ponctuels'],
      ['avis de navigation','fermetures saisonnières','déroutements'],
      'Aucun changement d’accès ou de navigation n’est observé pendant trois mois.',
      ['Navigation','Accès'], .50),
    S('ice-seasonal-adaptation', 'supply_fuel', .18, [2160,8760], .52,
      g => `Cryosphère : possibilité d’adaptation des routes saisonnières et de la logistique autour de ${g}.`,
      g => `Si l’anomalie persiste, opérateurs et territoires peuvent ajuster leurs calendriers et itinéraires sur une saison.`,
      'Le scénario dépend d’une anomalie durable, pas d’un événement isolé.',
      ['anomalie persistante','fiabilité réduite des routes saisonnières','adaptation logistique','nouveaux calendriers'],
      ['changements d’itinéraire','saisons d’accès raccourcies','coûts logistiques'],
      'Les conditions saisonnières reviennent à la normale sans adaptation opérationnelle notable.',
      ['Logistique','Saisonnalité'], .40)
  ],
  air_quality_hazard: [
    S('air-health-guidance', 'public_health', .42, [0,168], .76,
      g => `Qualité de l’air : risque de recommandations sanitaires renforcées autour de ${g}.`,
      g => `Un épisode de pollution peut rapidement déclencher recommandations, restrictions locales et hausse des consultations sensibles.`,
      'Un danger de qualité de l’air est signalé.',
      ['pollution élevée','exposition de la population','recommandations sanitaires','comportements adaptés'],
      ['indices de pollution élevés','alertes sanitaires','restrictions locales'],
      'Les niveaux de pollution retombent sans alerte ni effet sanitaire notable dans la semaine.',
      ['Santé','Air'], .82),
    S('air-productivity', 'economy_labor', .26, [72,720], .60,
      g => `Qualité de l’air : risque d’absences, baisse d’activité extérieure et pression sanitaire locale autour de ${g}.`,
      g => `Si l’épisode dure, les effets peuvent toucher travail extérieur, écoles et consultations.`,
      'Les impacts économiques apparaissent surtout lorsque l’exposition dure plusieurs jours.',
      ['pollution persistante','activité extérieure limitée','absences / consultations','productivité locale réduite'],
      ['fermetures d’activités','hausse des consultations','consignes employeurs'],
      'L’épisode reste bref sans impact mesurable sur activité ou santé.',
      ['Travail','Écoles','Santé'], .58)
  ],
  severe_winter_hazard: [
    S('winter-transport-power', 'weather_climate', .45, [0,120], .78,
      g => `Épisode hivernal : risque de retards de transport et de coupures ponctuelles autour de ${g}.`,
      g => `Neige, gel ou verglas peuvent rapidement perturber routes, rail et électricité.`,
      'Un épisode hivernal sévère est signalé.',
      ['neige / gel','réseaux exposés','retards et accidents','services perturbés'],
      ['annulations','fermetures routières','coupures électriques'],
      'L’épisode passe sans perturbation significative des transports ou réseaux.',
      ['Transport','Électricité'], .84),
    S('winter-energy-demand', 'energy', .32, [24,336], .66,
      g => `Froid : risque de hausse temporaire de la demande énergétique autour de ${g}.`,
      g => `Une vague de froid peut pousser rapidement la demande de chauffage et tendre certains marchés locaux.`,
      'Les températures très basses augmentent généralement la demande de chauffage.',
      ['froid marqué','demande de chauffage','consommation énergétique en hausse','tension locale possible'],
      ['pics de consommation','prix spot énergie','alertes réseau'],
      'La demande énergétique reste normale malgré l’épisode froid.',
      ['Énergie','Chauffage'], .68)
  ],
  temperature_extreme: [
    S('heat-health-power', 'weather_climate', .45, [0,168], .78,
      g => `Températures extrêmes : risque de pression simultanée sur santé et électricité autour de ${g}.`,
      g => `Les prochaines journées peuvent concentrer surmortalité, demande de climatisation et stress réseau.`,
      'Un épisode de température extrême est actif.',
      ['température extrême','exposition humaine et énergétique','demande de soins / électricité','pression locale'],
      ['alertes chaleur/froid','pics de consommation','hausse des urgences'],
      'L’épisode s’atténue sans pression notable sur santé ou électricité.',
      ['Santé','Électricité'], .88),
    S('heat-water-crops', 'supply_fuel', .32, [72,720], .68,
      g => `Températures extrêmes : risque de stress hydrique et agricole autour de ${g}.`,
      g => `Si l’épisode persiste, eau, élevage et cultures peuvent devenir les prochains points de tension.`,
      'Les impacts agricoles augmentent avec la durée de l’épisode et l’état initial des sols.',
      ['températures persistantes','sols / eau sous pression','rendements et élevage exposés','révisions agricoles'],
      ['restrictions d’eau','alertes agricoles','révisions de rendement'],
      'Aucune tension hydrique ou agricole significative n’est observée dans le mois.',
      ['Eau','Agriculture'], .70),
    S('heat-seasonal-prices', 'economy_labor', .21, [720,4320], .56,
      g => `Si l’épisode se répète : risque de coûts saisonniers plus élevés sur énergie, agriculture ou assurance autour de ${g}.`,
      g => `Des épisodes répétés peuvent se transmettre aux coûts économiques sur plusieurs mois.`,
      'Ce scénario de moyen terme dépend de la répétition des extrêmes, pas d’un seul jour chaud ou froid.',
      ['extrêmes répétés','coûts opérationnels élevés','pertes ou demande énergétique','révisions de prix / assurance'],
      ['sinistres en hausse','prix agricoles','factures énergétiques saisonnières'],
      'Les conditions se normalisent sans hausse durable des coûts saisonniers.',
      ['Prix','Assurance','Énergie'], .50)
  ],
  water_quality_anomaly: [
    S('water-advisory', 'public_health', .42, [0,336], .72,
      g => `Eau : risque d’avis sanitaires ou de restrictions d’usage autour de ${g}.`,
      g => `Une anomalie de qualité de l’eau peut déclencher contrôles, avis de consommation et restrictions locales.`,
      'Une anomalie de qualité de l’eau est suivie par les observateurs.',
      ['anomalie détectée','analyses supplémentaires','avis sanitaire','usages adaptés'],
      ['avis de non-consommation','fermetures de baignade','contrôles renforcés'],
      'Les analyses reviennent normales sans avis ni restriction dans deux semaines.',
      ['Eau','Santé'], .76),
    S('water-local-costs', 'economy_labor', .25, [168,1440], .58,
      g => `Eau : risque de coûts supplémentaires pour traitement, agriculture ou activités locales autour de ${g}.`,
      g => `Une restriction prolongée peut déplacer le problème vers les coûts de traitement et les usages économiques.`,
      'Les effets économiques dépendent de la durée et des usages touchés.',
      ['restriction prolongée','traitement supplémentaire','usages économiques contraints','coûts locaux en hausse'],
      ['coûts de traitement','restrictions agricoles','fermetures d’activités'],
      'La qualité se normalise sans coût économique notable.',
      ['Traitement','Agriculture'], .52)
  ],
  natural_hazard_event: [
    S('hazard-access', 'natural_hazards', .28, [0,168], .58,
      g => `Événement naturel : risque de contraintes d’accès et de services autour de ${g}.`,
      g => `L’événement reste à qualifier, mais les premières conséquences probables concernent accès et services locaux.`,
      'Un événement naturel actif est détecté sans classification plus précise.',
      ['événement actif','zone exposée','accès / services surveillés','perturbations possibles'],
      ['fermetures','évacuations','alertes officielles'],
      'Aucune perturbation d’accès ou de service n’apparaît dans la semaine.',
      ['Accès','Services'], .42)
  ],
  financial_stress: [
    S('finance-risk-off', 'financial_stress', .35, [24,336], .76,
      () => 'Marchés : risque de durcissement rapide de l’aversion au risque et des conditions de financement.',
      () => 'La volatilité élevée peut rapidement se transmettre au crédit, aux émissions et aux actifs risqués.',
      'Les indicateurs officiels de volatilité financière se tendent.',
      ['volatilité en hausse','appétit pour le risque réduit','financement plus strict','pression sur actifs risqués'],
      ['VIX persistant > 25','élargissement des spreads','baisse des émissions de crédit'],
      'La volatilité et les spreads se normalisent durablement dans les deux semaines.',
      ['Marchés','Crédit'], .90),
    S('finance-capex-hiring', 'economy_labor', .27, [336,2160], .67,
      () => 'Économie : risque de décisions d’investissement et d’embauche plus prudentes si le stress financier persiste.',
      () => 'Un stress de marché prolongé peut devenir un frein concret au financement des entreprises en quelques mois.',
      'La transmission vers l’économie réelle dépend de la durée du stress et du crédit.',
      ['stress financier persistant','financement plus coûteux','investissements différés','embauches plus prudentes'],
      ['guidances d’entreprises','conditions bancaires','baisse des investissements'],
      'Les conditions financières se détendent sans ralentissement observable des investissements ou embauches.',
      ['Investissement','Emploi'], .70),
    S('finance-policy-response', 'financial_stress', .20, [2160,8760], .58,
      () => 'À moyen terme : probabilité accrue de réponse monétaire ou réglementaire si les tensions financières durent.',
      () => 'Une tension durable peut forcer banques centrales ou régulateurs à ajuster liquidité, supervision ou trajectoire de taux.',
      'Ce scénario dépend d’une persistance des tensions, pas d’un simple pic de volatilité.',
      ['stress durable','conditions financières serrées','risque macro visible','réponse de politique économique'],
      ['facilités de liquidité','changement de guidance monétaire','mesures prudentielles'],
      'Le stress se résorbe sans réponse monétaire ou réglementaire spécifique dans l’année.',
      ['Banques centrales','Régulation'], .54)
  ],
  credit_stress: [
    S('credit-tightening', 'financial_stress', .37, [72,720], .80,
      () => 'Crédit : risque de resserrement des conditions de financement des entreprises.',
      () => 'L’élargissement des spreads peut rapidement renchérir refinancements et nouvelles émissions.',
      'Les spreads de crédit se détériorent.',
      ['spreads en hausse','prime de risque plus élevée','financement plus cher','émissions et refinancements plus difficiles'],
      ['spreads HY en hausse','dégradation des émissions','conditions bancaires plus strictes'],
      'Les spreads retombent sans durcissement observable du financement dans le mois.',
      ['Crédit','Entreprises'], .90),
    S('credit-defaults', 'financial_stress', .29, [720,4320], .71,
      () => 'Crédit : risque de hausse des défauts et restructurations si le coût du refinancement reste élevé.',
      () => 'La tension du crédit peut mettre plusieurs mois à apparaître dans les défauts et restructurations.',
      'Les entreprises fragiles deviennent plus vulnérables lorsque les conditions de refinancement restent tendues.',
      ['crédit cher','murs de refinancement','trésoreries fragiles','défauts / restructurations'],
      ['défauts en hausse','restructurations','dégradation des notations'],
      'Les défauts restent stables et les refinancements se déroulent normalement dans six mois.',
      ['Défauts','Refinancement'], .72),
    S('credit-real-economy', 'economy_labor', .22, [2160,8760], .61,
      () => 'Économie : risque de ralentissement de l’investissement et de l’emploi si le crédit reste durablement tendu.',
      () => 'Un crédit cher pendant plusieurs trimestres peut peser sur investissement, immobilier et embauches.',
      'La transmission à l’économie réelle est plus lente que la réaction initiale des marchés.',
      ['crédit durablement cher','investissements reportés','demande plus faible','emploi plus prudent'],
      ['enquêtes de crédit','investissement des entreprises','données d’emploi'],
      'Le crédit se normalise sans ralentissement économique observable dans l’année.',
      ['Investissement','Emploi','Immobilier'], .60)
  ],
  energy_price_spike: [
    S('oil-fuel-freight', 'energy', .41, [72,504], .78,
      () => 'Énergie : risque de transmission de la hausse du pétrole vers carburants et fret.',
      () => 'La première transmission attendue concerne les carburants, le transport et certains coûts logistiques.',
      'Le pétrole accélère sur les données FRED.',
      ['pétrole en hausse','coûts d’approvisionnement','carburants / fret','coûts aval plus élevés'],
      ['prix de gros carburants','indices de fret','révisions de marges transport'],
      'Le pétrole reperd rapidement sa hausse et carburants ou fret ne se tendent pas.',
      ['Carburants','Fret'], .88),
    S('oil-inflation-consumer', 'economy_labor', .33, [336,2160], .70,
      () => 'Inflation : risque de pression supplémentaire sur certains prix et sur le budget des ménages si le pétrole reste élevé.',
      () => 'Une hausse durable du pétrole peut se transmettre à l’inflation et réduire le pouvoir d’achat disponible en quelques mois.',
      'L’effet macro dépend de la durée de la hausse énergétique.',
      ['énergie chère','transport et production plus coûteux','prix à la consommation','budget des ménages comprimé'],
      ['inflation énergie','prix à la pompe','confiance des ménages'],
      'Le pétrole se normalise sans transmission visible à l’inflation ou aux dépenses des ménages.',
      ['Inflation','Ménages'], .76),
    S('oil-transition-investment', 'energy', .20, [2160,17520], .60,
      () => 'À plus long terme : hausse probable des investissements de substitution énergétique si les prix élevés persistent.',
      () => 'Des prix durablement élevés peuvent accélérer efficacité énergétique, substitution et investissements alternatifs sur un à deux ans.',
      'Ce scénario dépend d’un niveau de prix durable, pas d’un pic de quelques jours.',
      ['énergie chère durable','rentabilité des alternatives','arbitrages d’investissement','substitution énergétique'],
      ['capex efficacité énergétique','ventes de solutions alternatives','politiques d’incitation'],
      'Les prix se normalisent sans accélération mesurable des investissements de substitution dans les deux ans.',
      ['Transition','Investissement'], .58)
  ],
  energy_price_relief: [
    S('oil-relief-freight', 'energy', .40, [72,504], .74,
      () => 'Énergie : possibilité d’un relâchement des pressions sur carburants et fret si la baisse du pétrole se confirme.',
      () => 'La baisse du pétrole peut d’abord détendre les coûts de transport et de carburants.',
      'La trajectoire du pétrole s’oriente nettement à la baisse.',
      ['pétrole en baisse','coût d’approvisionnement réduit','carburants / fret plus détendus','pression aval moindre'],
      ['confirmation WTI/Brent','prix de gros carburants','indices de fret'],
      'Le pétrole rebondit ou la baisse ne se transmet pas aux coûts aval.',
      ['Carburants','Fret'], .82),
    S('oil-relief-inflation', 'economy_labor', .29, [336,2160], .66,
      () => 'Inflation : possibilité d’un léger relâchement si la détente énergétique dure plusieurs semaines.',
      () => 'Une baisse durable de l’énergie peut enlever une partie de la pression sur les prix et le budget des ménages.',
      'La transmission désinflationniste est plus lente que la baisse initiale du pétrole.',
      ['énergie moins chère','coûts de transport réduits','inflation énergie en baisse','pression ménages moindre'],
      ['inflation énergie','prix à la pompe','anticipations inflation'],
      'Le pétrole rebondit ou l’inflation énergétique ne se détend pas dans trois mois.',
      ['Inflation','Ménages'], .66)
  ],
  labor_market_softening: [
    S('labor-hiring', 'economy_labor', .37, [336,1440], .74,
      () => 'Emploi US : risque de ralentissement des embauches et de remontée du chômage dans les prochaines semaines.',
      () => 'La hausse des inscriptions au chômage peut précéder un ralentissement plus visible des recrutements.',
      'Les inscriptions au chômage se détériorent rapidement.',
      ['claims en hausse','licenciements plus visibles','embauches prudentes','marché du travail plus faible'],
      ['claims persistants','JOLTS / payrolls','annonces de licenciements'],
      'Les inscriptions se normalisent et les données d’emploi restent solides pendant deux mois.',
      ['Emploi','Recrutement'], .86),
    S('labor-consumption', 'economy_labor', .28, [720,4320], .64,
      () => 'Ménages US : risque de consommation plus prudente si le marché du travail se refroidit.',
      () => 'Un ralentissement durable de l’emploi peut ensuite peser sur confiance, salaires et dépenses.',
      'La consommation réagit généralement avec retard à la détérioration du marché du travail.',
      ['emploi moins dynamique','revenus anticipés plus faibles','confiance en baisse','consommation prudente'],
      ['confiance consommateurs','croissance des salaires','ventes au détail'],
      'L’emploi ralentit sans effet visible sur confiance ou consommation dans six mois.',
      ['Ménages','Consommation'], .68),
    S('labor-policy', 'financial_stress', .20, [2160,8760], .56,
      () => 'Politique monétaire US : probabilité accrue d’un biais plus accommodant si le marché du travail continue de se dégrader.',
      () => 'Une faiblesse durable de l’emploi peut modifier la balance des risques de la banque centrale sur plusieurs trimestres.',
      'Ce scénario suppose une détérioration persistante, pas un seul chiffre hebdomadaire.',
      ['emploi durablement plus faible','pression inflationniste compatible','risque macro accru','biais monétaire plus accommodant'],
      ['guidance Fed','projections de taux','données payrolls / chômage'],
      'Le marché du travail se stabilise sans changement de biais monétaire dans l’année.',
      ['Taux','Banque centrale'], .52)
  ],
  media_supply_chain_signal: [
    S('supply-delays', 'supply_fuel', .34, [48,504], .66,
      () => 'Commerce mondial : risque de retards logistiques plus visibles si les tensions portuaires et maritimes se confirment.',
      () => 'Une convergence de signaux sur ports et transport peut précéder des retards concrets de livraison.',
      'Plusieurs médias et zones de publication convergent sur des tensions logistiques.',
      ['signaux logistiques convergents','capacité / itinéraires perturbés','délais de transport','retards d’approvisionnement'],
      ['fermetures de ports','déroutements','hausse des délais ou du fret'],
      'La convergence médiatique retombe sans perturbation confirmée des délais ou itinéraires.',
      ['Ports','Fret','Délais'], .80),
    S('supply-inventory-prices', 'supply_fuel', .27, [336,2160], .60,
      () => 'Approvisionnement : risque de tensions sur stocks et certains prix si les retards maritimes persistent plusieurs semaines.',
      () => 'Les retards deviennent économiquement visibles lorsqu’ils commencent à toucher stocks, délais clients et coûts de fret.',
      'La transmission vers les prix dépend de la durée et de la capacité de substitution des routes.',
      ['retards persistants','stocks de sécurité consommés','fret plus cher','prix / délais clients sous pression'],
      ['inventaires','délais fournisseurs','indices de fret'],
      'Les routes se normalisent sans effet mesurable sur stocks ou prix dans trois mois.',
      ['Stocks','Prix','Industrie'], .66),
    S('supply-diversification', 'geopolitics_security', .18, [2160,17520], .56,
      () => 'À plus long terme : probabilité accrue de diversification des fournisseurs et itinéraires si les disruptions se répètent.',
      () => 'Des perturbations répétées peuvent transformer une crise logistique en décision stratégique de sourcing sur un à deux ans.',
      'Ce scénario dépend d’une répétition des perturbations, pas d’un incident isolé.',
      ['disruptions répétées','coûts de dépendance visibles','arbitrages de sourcing','diversification des fournisseurs'],
      ['nouveaux contrats fournisseurs','relocalisation partielle','routes alternatives durables'],
      'Aucun changement significatif de sourcing ou d’itinéraire n’apparaît dans les deux ans.',
      ['Sourcing','Industrie'], .52)
  ],
  media_civil_disruption: [
    S('civil-service-disruption', 'social_collective_behavior', .34, [24,168], .64,
      () => 'Mobilisations : risque de perturbations de transport ou de services si grèves et protestations gagnent en ampleur.',
      () => 'Une mobilisation en croissance peut rapidement produire des blocages, annulations ou fermetures.',
      'Une convergence médiatique multi-source signale des mobilisations importantes.',
      ['mobilisation en hausse','participation croissante','points de blocage','services perturbés'],
      ['appels syndicaux','fermetures / blocages','annulations'],
      'La mobilisation se dissipe sans blocage ou perturbation de services dans la semaine.',
      ['Transport','Services'], .80),
    S('civil-negotiation', 'regulation_policy', .22, [168,720], .54,
      () => 'Mobilisations : probabilité accrue de négociations, concessions ou ajustements institutionnels si la pression persiste.',
      () => 'Lorsque la perturbation dure, la prochaine étape peut devenir politique ou contractuelle plutôt qu’opérationnelle.',
      'La réponse dépend de la durée, de l’ampleur et des acteurs impliqués.',
      ['mobilisation durable','coût économique ou politique','négociations','ajustements ou concessions'],
      ['ouverture de négociations','annonces gouvernementales / employeurs','accords sectoriels'],
      'La mobilisation s’achève sans négociation ni ajustement significatif dans le mois.',
      ['Négociation','Politique publique'], .50)
  ],
  media_geopolitical_trade: [
    S('trade-price-flow', 'geopolitics_security', .34, [72,720], .68,
      () => 'Commerce : risque de tension sur certains prix ou flux si les restrictions commerciales se matérialisent.',
      () => 'Sanctions, interdictions d’export ou contrôles peuvent rapidement modifier prix, volumes et itinéraires.',
      'Les signaux médiatiques convergent sur sanctions, interdictions d’export ou restrictions commerciales.',
      ['restriction commerciale','offre / itinéraires contraints','substitution plus coûteuse','pression sur prix ou délais'],
      ['texte réglementaire','réaction des exportateurs','prix / volumes concernés'],
      'Les restrictions annoncées ne sont pas appliquées ou n’affectent pas les flux dans le mois.',
      ['Commerce','Prix','Sanctions'], .84),
    S('trade-substitution', 'supply_fuel', .27, [720,4320], .62,
      () => 'Chaînes d’approvisionnement : probabilité de substitutions de fournisseurs et routes si les restrictions durent plusieurs mois.',
      () => 'Une restriction durable pousse les entreprises à chercher d’autres fournisseurs, pays ou itinéraires.',
      'La substitution prend plus de temps que la réaction initiale des marchés.',
      ['restriction durable','coût de dépendance','recherche d’alternatives','nouveaux fournisseurs / routes'],
      ['nouveaux contrats','détournement de flux commerciaux','investissements de capacité'],
      'Les restrictions disparaissent ou les flux initiaux reprennent sans substitution notable.',
      ['Sourcing','Commerce'], .66),
    S('trade-regionalization', 'geopolitics_security', .17, [4320,26280], .54,
      () => 'À horizon 1–3 ans : risque de régionalisation accrue des chaînes de valeur si les restrictions se répètent.',
      () => 'Des frictions commerciales répétées peuvent transformer des solutions temporaires en choix d’investissement durables.',
      'Ce scénario stratégique nécessite une répétition des restrictions et des investissements réels.',
      ['frictions répétées','substitution temporaire','capex géographique','chaînes de valeur plus régionales'],
      ['investissements de relocalisation','accords commerciaux régionaux','capacité industrielle déplacée'],
      'Les flux mondiaux se normalisent sans changement durable d’investissement ou de sourcing dans trois ans.',
      ['Industrie','Géopolitique','Investissement'], .54)
  ],
  media_financial_stress: [
    S('bank-liquidity', 'financial_stress', .28, [24,336], .60,
      () => 'Banques : risque de contagion de défiance si les signaux de liquidité se confirment par des données officielles.',
      () => 'Une convergence médiatique sur liquidité peut précéder retraits, interventions ou tensions interbancaires.',
      'Des médias indépendants convergent sur un stress bancaire ou de liquidité.',
      ['signal de défiance','retraits / tension de liquidité','réponse banques / autorités','contagion éventuelle'],
      ['données de dépôts','facilités de liquidité','communiqués régulateurs'],
      'Aucune donnée officielle ne confirme le stress et les signaux médiatiques disparaissent dans les deux semaines.',
      ['Banques','Liquidité'], .72),
    S('bank-credit-slowdown', 'financial_stress', .21, [336,2160], .54,
      () => 'Banques : risque de crédit plus prudent si le stress de liquidité persiste.',
      () => 'Même sans crise systémique, un épisode de stress peut conduire les banques à durcir temporairement l’octroi de crédit.',
      'La transmission au crédit dépend de la persistance et de la confirmation officielle du stress.',
      ['stress bancaire persistant','gestion de bilan plus prudente','standards de crédit durcis','financement plus rare'],
      ['enquêtes de crédit','croissance des prêts','conditions bancaires'],
      'Le stress disparaît sans resserrement observable des conditions de crédit.',
      ['Crédit','Banques'], .54)
  ],
  media_cyber_disruption: [
    S('cyber-service-disruption', 'cyber_technology', .30, [12,168], .60,
      () => 'Cyber : risque de perturbations opérationnelles plus visibles si les attaques convergentes touchent des services critiques.',
      () => 'Une hausse de signaux cyber peut précéder indisponibilités, ralentissements ou procédures de secours.',
      'Plusieurs sources médiatiques convergent sur des incidents cyber à fort impact.',
      ['incidents convergents','systèmes isolés / ralentis','services dégradés','procédures de continuité'],
      ['interruptions de service','communications d’incident','activation de plans de continuité'],
      'Aucune perturbation opérationnelle confirmée n’apparaît dans la semaine.',
      ['Cyber','Services critiques'], .74),
    S('cyber-security-spend', 'cyber_technology', .20, [720,4320], .54,
      () => 'Cyber : probabilité d’accélération des dépenses de sécurité et des audits après une vague d’incidents majeurs.',
      () => 'Les incidents visibles peuvent déplacer les budgets vers sécurité, sauvegardes et contrôle des fournisseurs sur plusieurs mois.',
      'Ce scénario dépend d’incidents confirmés et coûteux, pas d’une simple hausse médiatique.',
      ['incidents confirmés','coûts opérationnels','réévaluation du risque','budgets cyber renforcés'],
      ['guidance cyber des entreprises','nouveaux audits','dépenses de sécurité'],
      'Les incidents restent mineurs sans hausse observable des budgets ou audits dans six mois.',
      ['Cybersécurité','Investissement'], .52)
  ],
  media_conflict_escalation: [
    S('conflict-markets-logistics', 'geopolitics_security', .30, [24,336], .62,
      () => 'Géopolitique : risque de volatilité sur transport, énergie ou matières premières si l’escalade militaire se confirme.',
      () => 'Une escalade régionale peut rapidement toucher routes, primes de risque et marchés de matières premières.',
      'Les signaux médiatiques convergent sur une intensification militaire ou sécuritaire.',
      ['escalade sécuritaire','risque sur routes / infrastructures','primes de risque plus élevées','transport et marchés perturbés'],
      ['fermetures d’espace / routes','prix énergie / fret','alertes officielles'],
      'L’escalade se désamorce sans perturbation mesurable des routes ou marchés dans deux semaines.',
      ['Géopolitique','Énergie','Fret'], .80),
    S('conflict-trade-adjustment', 'supply_fuel', .23, [336,4320], .56,
      () => 'Géopolitique : probabilité d’ajustements de commerce, stocks et approvisionnements si la crise dure plusieurs mois.',
      () => 'Une crise prolongée peut pousser entreprises et États à sécuriser stocks, fournisseurs et itinéraires.',
      'La transmission stratégique dépend de la durée et de l’exposition économique de la zone.',
      ['crise durable','risque d’approvisionnement','stocks de sécurité','nouveaux fournisseurs / routes'],
      ['achats de précaution','déroutements durables','nouveaux contrats'],
      'La crise se résout sans modification durable des stocks ou approvisionnements dans six mois.',
      ['Stocks','Commerce'], .58),
    S('conflict-strategic-rearm', 'geopolitics_security', .15, [4320,26280], .50,
      () => 'À horizon 1–3 ans : risque d’investissements supplémentaires en défense, sécurité et résilience si les tensions persistent.',
      () => 'Des tensions répétées peuvent déplacer durablement budgets publics et industriels vers sécurité et résilience.',
      'Ce scénario exige une persistance des tensions et des décisions budgétaires concrètes.',
      ['tensions répétées','vulnérabilités stratégiques','arbitrages budgétaires','investissements de sécurité'],
      ['budgets défense / sécurité','contrats industriels','plans de résilience'],
      'Les tensions se normalisent sans hausse durable des investissements de sécurité dans trois ans.',
      ['Défense','Résilience','Industrie'], .50)
  ],
  copernicus_emergency_activation: [
    S('cems-access', 'natural_hazards', .35, [0,168], .68,
      g => `Crise suivie par satellite : risque de contraintes logistiques et d’accès autour de ${g}.`,
      g => `Une activation Copernicus indique qu’une cartographie opérationnelle est nécessaire ; accès et secours sont les prochains points à surveiller.`,
      'Copernicus EMS a activé une cartographie d’urgence.',
      ['activation d’urgence','cartographie de dommages','adaptation des accès et secours','contraintes logistiques'],
      ['cartes de dommages','évacuations','routes / réseaux affectés'],
      'L’activation se clôt sans dommage ni contrainte opérationnelle significative dans la semaine.',
      ['Secours','Logistique'], .80),
    S('cems-recovery', 'economy_labor', .26, [168,1440], .60,
      g => `Crise suivie par satellite : probabilité de besoins de réparation et de remise en service autour de ${g}.`,
      g => `Si les dommages sont confirmés, la demande peut se déplacer vers réparation, logistique humanitaire et remise en état.`,
      'La cartographie d’urgence peut révéler des besoins qui persistent après la première semaine.',
      ['dommages cartographiés','besoins confirmés','réparation / secours','remise en service'],
      ['estimations de dommages','plans de réparation','aide humanitaire'],
      'Aucun besoin significatif de réparation ou de remise en service n’est identifié dans les deux mois.',
      ['Réparation','Humanitaire'], .60)
  ]
};

// Scénarios stratégiques : volontairement plus incertains et conditionnés à la persistance des signaux.
SCENARIOS.drought_emergency.push(
  S('drought-water-strategy', 'regulation_policy', .11, [3*YEAR_HOURS,5*YEAR_HOURS], .48,
    g => `À horizon 3–5 ans : possibilité d’une transformation durable de la gestion de l’eau autour de ${g}.`,
    g => `Si le stress hydrique se répète, les décisions peuvent finir par toucher infrastructures, usages et aménagement du territoire.`,
    'Ce scénario stratégique n’est activé que comme prolongement conditionnel d’un stress hydrique déjà observable.',
    ['sécheresses répétées','coûts récurrents','investissements d’adaptation','gestion de l’eau transformée'],
    ['plans pluriannuels eau','grands investissements de stockage / réseau','révisions durables des usages'],
    'Aucune transformation durable de la politique ou des infrastructures de l’eau n’apparaît dans cinq ans.',
    ['Eau','Aménagement','Infrastructure'], .48)
);
SCENARIOS.media_geopolitical_trade.push(
  S('trade-industrial-geography', 'geopolitics_security', .10, [3*YEAR_HOURS,5*YEAR_HOURS], .46,
    () => 'À horizon 3–5 ans : possibilité d’un déplacement durable de certaines capacités industrielles si les frictions commerciales persistent.',
    () => 'Des restrictions répétées peuvent finir par déplacer non seulement les flux, mais aussi les lieux d’investissement et de production.',
    'Ce scénario de très long terme exige des frictions répétées et des décisions d’investissement visibles.',
    ['frictions commerciales répétées','substitution durable','nouveaux investissements','géographie industrielle déplacée'],
    ['nouvelles usines / capacités','aides à la relocalisation','flux d’investissement modifiés'],
    'Aucun déplacement durable des capacités ou investissements n’est visible dans cinq ans.',
    ['Industrie','Investissement','Géopolitique'], .46)
);
SCENARIOS.media_conflict_escalation.push(
  S('conflict-security-architecture', 'geopolitics_security', .09, [3*YEAR_HOURS,5*YEAR_HOURS], .44,
    () => 'À horizon 3–5 ans : possibilité d’une architecture de sécurité plus coûteuse et plus régionalisée si les tensions deviennent chroniques.',
    () => 'Une succession de crises peut finir par modifier durablement budgets, alliances opérationnelles et capacités industrielles de sécurité.',
    'Il s’agit d’un scénario stratégique à faible base, conditionné à la répétition des tensions.',
    ['crises répétées','budgets de sécurité en hausse','capacités industrielles renforcées','architecture régionale durable'],
    ['budgets pluriannuels','contrats industriels','accords de sécurité durables'],
    'Les tensions se normalisent sans transformation durable des budgets ou capacités de sécurité dans cinq ans.',
    ['Sécurité','Défense','Industrie'], .44)
);

function normalizeGeo(value) {
  return String(value || 'Monde').toLowerCase().replace(/[^a-z0-9à-ÿ]+/gi, ' ').trim().slice(0, 96);
}

function hoursSince(at) {
  const t = new Date(at).getTime();
  return Number.isFinite(t) ? Math.max(0, (Date.now() - t) / HOUR) : 24;
}

function horizonMeta(hours) {
  const end = hours[1];
  if (end <= 72) return { tier: 'immediate', label: 'Prochaines heures', order: 0 };
  if (end <= 30 * DAY_HOURS) return { tier: 'near', label: 'Jours & semaines', order: 1 };
  if (end <= YEAR_HOURS) return { tier: 'medium', label: 'Mois à venir', order: 2 };
  if (end <= 3 * YEAR_HOURS) return { tier: 'long', label: '1–3 ans', order: 3 };
  return { tier: 'strategic', label: '3–5 ans', order: 4 };
}

function humanWindow([low, high]) {
  if (high <= 72) return low <= 0 ? `dans les prochaines ${high} h` : `entre ${low} et ${high} h`;
  const lowDays = low / 24;
  const highDays = high / 24;
  if (highDays <= 45) return lowDays < 1 ? `dans les ${Math.round(highDays)} prochains jours` : `d’ici ${Math.max(1, Math.round(lowDays))} à ${Math.round(highDays)} jours`;
  const lowMonths = lowDays / 30.44;
  const highMonths = highDays / 30.44;
  if (highMonths <= 18) return `d’ici ${Math.max(1, Math.round(lowMonths))} à ${Math.round(highMonths)} mois`;
  const lowYears = lowDays / 365;
  const highYears = highDays / 365;
  return `d’ici ${Math.max(1, Math.round(lowYears))} à ${Math.max(1, Math.round(highYears))} ans`;
}

function timeWindow(scenario) {
  const now = new Date();
  const start = new Date(now.getTime() + scenario.hours[0] * HOUR);
  const end = new Date(now.getTime() + scenario.hours[1] * HOUR);
  return {
    kind: 'relative_after_precursor',
    low_hours: scenario.hours[0], high_hours: scenario.hours[1],
    start_at: start.toISOString(), end_at: end.toISOString(),
    target_date: end.toISOString(), human: humanWindow(scenario.hours),
    ...horizonMeta(scenario.hours)
  };
}

function horizonPenalty(scenario) {
  const end = scenario.hours[1];
  if (end > 3 * YEAR_HOURS) return .42;
  if (end > YEAR_HOURS) return .30;
  if (end > 180 * DAY_HOURS) return .20;
  if (end > 60 * DAY_HOURS) return .11;
  return 0;
}

function probabilityFor(signals, scenario) {
  const trust = signals.reduce((s, x) => s + x.source_trust, 0) / signals.length;
  const severity = Math.max(...signals.map(x => clamp(Number(x.severity) || .5, 0, 1)));
  const families = new Set(signals.map(x => x.source_family)).size;
  const freshness = Math.max(0, 1 - Math.min(...signals.map(x => hoursSince(x.observed_at))) / 72);
  const corroboration = clamp((signals.length - 1) / 4, 0, 1);
  let z = logit(scenario.prior);
  z += (trust - .72) * 1.85;
  z += (severity - .5) * 1.05;
  z += clamp(families - 1, 0, 3) * .17;
  z += freshness * .22;
  z += corroboration * .20;
  z -= horizonPenalty(scenario);
  const projection = signals.map(s => s.facts?.statistical_projection).find(Boolean);
  if (projection && Number.isFinite(projection.change)) z += Math.min(.26, Math.abs(projection.change) * 1.45);
  const estimate = clamp(sigmoid(z), .06, .90);
  const horizon = horizonMeta(scenario.hours);
  const uncertaintyExtra = horizon.order * .018;
  const half = clamp(.13 + uncertaintyExtra + (1 - scenario.pattern) * .07 + (families === 1 ? .025 : 0), .11, .24);
  return {
    type: 'model_estimate', estimate,
    percent: Math.round(estimate * 100),
    interval_low: clamp(estimate - half, .02, .95),
    interval_high: clamp(estimate + half, .05, .97),
    interval_percent: [Math.round(clamp(estimate - half, .02, .95) * 100), Math.round(clamp(estimate + half, .05, .97) * 100)],
    method: 'evidence-node-log-odds-v2-multi-horizon',
    calibration_status: 'uncalibrated_model_estimate', empirically_calibrated: false,
    can_be_read_as_empirical_frequency: false
  };
}

function consolidation(signals, scenario, probability) {
  const trust = signals.reduce((s, x) => s + x.source_trust, 0) / signals.length;
  const families = new Set(signals.map(x => x.source_family)).size;
  const freshness = Math.max(0, 1 - Math.min(...signals.map(x => hoursSince(x.observed_at))) / 72);
  const diversity = clamp((families - 1) / 3, 0, 1);
  const corroboration = clamp((signals.length - 1) / 4, 0, 1);
  const score = Math.round(100 * (0.30 * trust + 0.18 * diversity + 0.16 * freshness + 0.22 * scenario.pattern + 0.14 * corroboration));
  return {
    score, score_is_probability: false,
    level: score >= 78 ? 'très solide' : score >= 64 ? 'solide' : score >= 50 ? 'en consolidation' : 'fragile',
    source_families: [...new Map(signals.map(s => [s.source_family, { key: s.source_family, label: s.source_family }])).values()],
    source_providers: [...new Map(signals.map(s => [s.source_key, { key: s.source_key, label: s.source_label, role: s.source_family }])).values()],
    dimensions: [
      { key: 'source_quality', label: 'Qualité', score: Math.round(trust * 100) },
      { key: 'source_diversity', label: 'Diversité', score: Math.round(25 + diversity * 75) },
      { key: 'freshness', label: 'Fraîcheur', score: Math.round(freshness * 100) },
      { key: 'pattern', label: 'Mécanisme', score: Math.round(scenario.pattern * 100) },
      { key: 'corroboration', label: 'Corroboration', score: Math.round(35 + corroboration * 65) }
    ],
    strengths: [
      trust >= .9 ? 'Source principale officielle à forte fiabilité.' : null,
      families > 1 ? `${families} familles de sources soutiennent la trajectoire.` : null,
      signals.length > 1 ? `${signals.length} signaux compatibles convergent.` : null,
      scenario.pattern >= .75 ? 'Mécanisme de propagation bien défini.' : null
    ].filter(Boolean),
    weaknesses: [
      families === 1 ? 'Diversité de sources encore limitée.' : null,
      scenario.pattern < .65 ? 'Trajectoire encore exploratoire.' : null,
      horizonMeta(scenario.hours).order >= 3 ? 'Horizon long : incertitude structurellement plus élevée.' : null,
      probability.empirically_calibrated ? null : 'Estimation de modèle non encore calibrée empiriquement.'
    ].filter(Boolean)
  };
}

function groupSignals(signals) {
  const groups = new Map();
  const geographicTypes = new Set([
    'major_earthquake','wildfire_emergency','flood_emergency','severe_storm_emergency','volcanic_emergency','drought_emergency',
    'landslide_emergency','cryosphere_disruption','air_quality_hazard','severe_winter_hazard','temperature_extreme','water_quality_anomaly',
    'natural_hazard_event','disease_outbreak_signal','copernicus_emergency_activation'
  ]);
  for (const signal of signals) {
    if (!SCENARIOS[signal.event_type]?.length) continue;
    const geo = geographicTypes.has(signal.event_type) ? normalizeGeo(signal.geography || signal.title) : 'global';
    const key = `${signal.event_type}|${geo}`;
    const arr = groups.get(key) ?? [];
    arr.push(signal);
    groups.set(key, arr);
  }
  return groups;
}

function selectDiverse(rows, limit) {
  const selected = [];
  const selectedKeys = new Set();
  const domainCounts = new Map();
  const scenarioCounts = new Map();
  const originCounts = new Map();
  const horizonCounts = new Map();
  const horizonCaps = { immediate: 10, near: 12, medium: 10, long: 7, strategic: 5 };

  const accept = (row, relaxed = false) => {
    if (selectedKeys.has(row.scenario_key)) return false;
    const dc = domainCounts.get(row.domain) ?? 0;
    const sc = scenarioCounts.get(row.scenario_id) ?? 0;
    const oc = originCounts.get(row.origin_group) ?? 0;
    const hc = horizonCounts.get(row.horizon_tier) ?? 0;
    if (!relaxed) {
      if (dc >= 9 || sc >= 3 || oc >= 3 || hc >= (horizonCaps[row.horizon_tier] ?? 8)) return false;
    } else if (dc >= 12 || oc >= 4) return false;
    selected.push(row); selectedKeys.add(row.scenario_key);
    domainCounts.set(row.domain, dc + 1);
    scenarioCounts.set(row.scenario_id, sc + 1);
    originCounts.set(row.origin_group, oc + 1);
    horizonCounts.set(row.horizon_tier, hc + 1);
    return true;
  };

  for (const row of rows) {
    accept(row, false);
    if (selected.length >= limit) return selected;
  }
  for (const row of rows) {
    accept(row, true);
    if (selected.length >= limit) break;
  }
  return selected;
}

export function buildForecasts(signals, limit = 36) {
  const forecasts = [];
  for (const [groupKey, group] of groupSignals(signals)) {
    const representative = [...group].sort((a, b) => (b.severity ?? 0) - (a.severity ?? 0))[0];
    const geography = representative.geography || 'Monde';
    const providerLabels = [...new Set(group.map(s => s.source_label).filter(Boolean))].slice(0, 3);
    for (const scenario of SCENARIOS[representative.event_type] ?? []) {
      const probability = probabilityFor(group, scenario);
      const c = consolidation(group, scenario, probability);
      const window = timeWindow(scenario);
      const scenarioKey = hash(`${groupKey}|${scenario.id}`);
      const contrary = scenario.contrary.length ? scenario.contrary : [
        'les indicateurs intermédiaires attendus restent absents',
        'des sources indépendantes montrent une normalisation du mécanisme'
      ];
      const summary = scenario.summary(geography);
      const title = scenario.headline(geography);
      forecasts.push({
        id: scenarioKey, scenario_key: scenarioKey, scenario_id: scenario.id, origin_group: groupKey,
        status: 'active', domain: scenario.domain, event_type: representative.event_type,
        title, headline: title, outcome: title, summary, region: geography,
        public_language: 'fr', fact_status: 'forecast_from_precursor',
        horizon_tier: window.tier, horizon_label: window.label, horizon_order: window.order,
        target_date: window.target_date,
        trajectory: probability.percent >= 60 ? 'building' : probability.percent >= 36 ? 'forming' : 'fragile',
        probability, confidence: c.score, confidence_label: c.level,
        time_window: window,
        what_we_know: scenario.known,
        why_now: `${scenario.known} ${providerLabels.length ? `Les signaux de ${providerLabels.join(' + ')} placent maintenant cette trajectoire dans le radar ÉVIDENCE.` : 'Les signaux disponibles placent cette trajectoire dans le radar ÉVIDENCE.'}`,
        causal_chain: scenario.chain,
        watch_next: scenario.watch,
        favorable_signals: scenario.watch,
        contrary_signals: contrary,
        probability_up_if: scenario.watch,
        probability_down_if: contrary,
        human_needs: scenario.tags,
        resolution_conditions: `La trajectoire est considérée comme matérialisée si des éléments observables cohérents avec « ${scenario.chain.at(-1)} » apparaissent avant ${new Date(window.end_at).toLocaleDateString('fr-FR')}.`,
        falsification: scenario.falsify,
        evidence: group.slice(0, 6).map(s => ({
          title: s.title, source_key: s.source_key, source_label: s.source_label, source_family: s.source_family,
          source_trust: s.source_trust, url: s.url, observed_at: s.observed_at, event_at: s.event_at, facts: s.facts
        })),
        fusion: {
          engine: 'evidence-node-scenario-fusion-v2-multi-horizon', raw_signal_count: group.length,
          source_keys: [...new Set(group.map(s => s.source_key))], duplicate_probability_inflation_prevented: true,
          geography_aware_grouping: true, probability_recomputed_after_fusion: true,
          multiple_distinct_outcomes_per_precursor_allowed: true
        },
        consolidation: c,
        novelty: 'second_order_outcome',
        commercial_priority: scenario.interest,
        commercial_contract: { certainty_claimed: false, falsifiable: true, expiry_enforced: true }
      });
    }
  }

  forecasts.sort((a, b) => {
    const score = row => row.probability.percent + row.consolidation.score * .22 + row.commercial_priority * 12 - row.horizon_order * 1.4;
    return score(b) - score(a);
  });
  return selectDiverse(forecasts, limit);
}
