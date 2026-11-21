# PanSim – Corrected Commuting Matrix, Workplace Recalibration and Agent Assignment

**Munkajegyzet a szakdolgozathoz**  
**Dátum:** 2026. november 21.  
**Állapot:** A tavaszi foglalkoztatott–munkahely hozzárendelés lezárásra javasolt változata: **V3.3**. A teljes nyári populációhoz való újrakapcsolás még hátravan.  
**Javasolt szakdolgozati alcím:** *Recalibrated Workplace Capacities and Commuting-Constrained Agent Assignment* (a KSH mátrixot eredetileg **javítottuk**, a szintetikus OD-eloszlást **optimalizáltuk**; ez nem az eredeti KSH-mátrix átírása).

## 1. Feladat és adatok

A tavaszi pipeline csak **foglalkoztatottakat** és szintetikus **vállalati munkahelyeket** kezel; a lakásokkal, teljes népességgel, nem foglalkoztatottakkal és külföldön dolgozókkal való kapcsolat a későbbi, nyári pipeline feladata. A cél az egyéni foglalkoztatotti profilok és a cégek szabad dolgozói férőhelyeinek összekapcsolása úgy, hogy a munkavégzési **vármegye**, az ingázás iránya, valamint a kapacitások közelebb legyenek a KSH 2022-es referenciájához.

- Tavaszi `agents.csv`: **4 668 639 foglalkoztatott**, saját lakóvármegye, FEOR, TEÁOR és más profiljellemzők.
- Cégek: **954 003** rekord a `generated_companies_calibrated.csv` állományban; a `company_size` összege **4 658 011 dolgozói férőhely (worker slot)**. Ez **nem** 4 658 011 különálló munkahely.
- Javított KSH-belföldi mátrix: **4 596 079** foglalkoztatott. A referenciának és a tavaszi szintetikus ágensállománynak **eltér a létszáma**, ezért nem lehet minden kapcsolatot személyre pontosan visszaadni.
- Az országos férőhelyhiány: **10 628** (`4 668 639 − 4 658 011`), így ennyi ágens marad hozzárendelés nélkül, ha minden férőhely pontosan egyszer használható fel.

## 2. A hibák és javításuk sorrendben

1. **KSH-mátrix iránya:** a korábbi beolvasás felcserélte a lakóhelyi és munkahelyi vármegye szerepét. A `build_commuting_matrix_v2.py` ezt javította; a belföldi referencia a `04_commuting_matrix_v2_all_domestic.csv`. A KSH eredeti számait nem változtattuk meg.
2. **Régi munkahelykiosztás:** a TEÁOR-azonosság kedvéért túl sok dolgozót vitt más vármegyébe. A földrajzi cél elsőbbséget kapott; a feldolgozási sorrend kapacitáselszívó hatását a helyi kvóták tervezése váltotta fel.
3. **Kapacitások földrajzi torzulása:** a korábbi céggenerálás országos/TEÁOR célértékekhez igazított, de nem biztosított megyénként megfelelő dolgozói férőhelyeket. Budapest és Pest többlete mellett több más megyében hiány keletkezett.
4. **Vármegyei cégméret-rekalibrálás:** a cégek **számát, települését, TEÁOR-kódját és méretkategóriáját megtartva**, kizárólag a `company_size` értékeket módosítottuk a KSH munkahely szerinti megyearányaihoz. Mind a **20/20** megyei cél teljesült, a **4 658 011** országos férőhely változatlan maradt. **311 196** cég mérete változott; **0** cég lépett ki a saját méretkategóriájából. **22** TEÁOR-alágazat országos kapacitása módosult; ez összesen **7 323 slotnyi nettó ágazatok közötti eltolódásnak** felel meg (L1-eltérés: 14 646).
5. **V3–V3.3 kiosztási finomítás:** megyei kapacitás- és saját-megyei kvóták, majd a javított KSH OD (*origin–destination*, lakóvármegye → munkahelyvármegye) kapcsolatok együttes kiegyensúlyozása. A V3.2 az eloszlási eltérést csökkentette és vármegyék között osztotta el a 10 628 kiosztatlan dolgozót. A V3.3 megtartotta a V3.2 saját-megyei létszámait és kiosztatlan-eloszlását, és védett minimumokkal megakadályozta a nagyobb KSH-kapcsolatok majdnem nullára csökkenését.

**Példák a vállalati férőhelyek rekalibrálására:**

| Vármegye | Korábbi slot | Rekalibrált slot |
|---|---:|---:|
| Budapest | 1 617 667 | 1 235 858 |
| Pest | 657 451 | 509 304 |
| Borsod-Abaúj-Zemplén | 175 605 | 255 697 |
| Szabolcs-Szatmár-Bereg | 149 860 | 217 392 |
| Zala | 77 064 | 116 134 |

## 3. A V3.3 végső ellenőrzött összesítése

| Mutató | V3.3 |
|---|---:|
| Foglalkoztatott ágensek | **4 668 639** |
| Munkahelyhez rendelt ágensek | **4 658 011** |
| Kiosztatlan ágensek | **10 628** |
| Saját vármegyében dolgozók | **3 925 654 (84,086%)** |
| KSH saját vármegyei referencia | **84,086%** |
| Más vármegyében dolgozók | **732 357** |
| KSH más vármegyében dolgozók, összes belföldi kategória | **731 438** |
| Túlfoglalt cégek | **0** |
| Nem azonos TEÁOR-ral történt elhelyezés | **771 382** (435 294 helyi + 336 088 más megyei) |
| Megőrzött, a KSH-ban létező megyeközi irányok | **380/380** |

Az utolsó két TEÁOR-fallback adat **nem** azt jelenti, hogy az eredeti ágens TEÁOR-értéke módosult; csak a kiosztott cég ágazata térhet el. Az eredeti FEOR és TEÁOR adatok a kiosztóban változatlanul továbbmennek.

**Megyei kivételek:** húsz területből **18-ban** a saját vármegyében dolgozók aránya legfeljebb **1 százalékponttal** tér el a KSH-aránytól. Győr-Moson-Sopronban **89,150%** a KSH **94,263%** helyett (−5,113 pp); Vasban **89,679%** a KSH **92,314%** helyett (−2,636 pp). A tavaszi lakóhelyi dolgozói összlétszám és a rögzített céges kapacitás nem engedi minden helyi célt és minden bejáró forgalmat egyszerre pontosan teljesíteni.

## 4. Ingázási eloszlás – változatok összehasonlítása

A TV distance (*total variation distance*) a **megyék közötti ingázási irányok normalizált eloszlásának** eltérése a KSH OD-eloszlástól. Kisebb érték jobb egyezést jelent; a csak megyén belüli kapcsolatok ebből a mutatóból ki vannak zárva.

| Változat | Saját megyei arány | Megyeközi OD TV-eltérés |
|---|---:|---:|
| Eredeti V3, régi céges kapacitás | 75,652% | — |
| V3, rekalibrált kapacitás | 84,093% | 5,432% |
| V3.1, kiegyensúlyozott OD | 84,086% | 5,228% |
| V3.2, optimalizált OD és kiosztatlan-eloszlás | 84,086% | **3,870%** |
| **V3.3, védett KSH-kapcsolatok** | **84,086%** | **3,927%** |

A V3.3 minimális TV-romlást vállal a V3.2-höz képest, hogy a jelentős irányok ne essenek ki. A V3.2-ben **9 olyan megyeközi kapcsolat** volt, amelynél a KSH legalább 500 dolgozót jelzett, de a modell csak 1-et; a V3.3-ban **egyik sem maradt 1 főn**. A V3.2 és V3.3 között **160 megyeközi cella** változott; az OD-mátrix eltérésének abszolút összegéből számított minimális átrendezett tömeg **9 792 dolgozó**.

**Fennmaradó példa:** Győr-Moson-Sopron → Budapest: KSH **5 178**, V3.3 **10 607**. Az országos arányok tehát nem jelentik az összes megyei kapcsolat pontos reprodukálását.

## 5. Fontos módszertani korlátok – a szakdolgozatba is kerüljenek

- A **84,086%-os országos egyezés kalibrációs cél**, nem független validáció. Ugyanaz a KSH-referencia szolgált a céges kapacitások megyearányos beállításához és az OD-tervhez. A független ellenőrzéshez további, külön referencia vagy megtartott tesztstatisztika szükséges.
- A tavaszi `agents.csv` **nem tartalmaz tényleges lakótelepülést**, ezért a saját *településen* dolgozók aránya és a településszintű ingázás ebben a lépésben nincs validálva.
- A javított KSH-adatokban az otthon dolgozók (**317 245**), lakótelepülésen dolgozók (**2 427 801**), más magyar településen dolgozók (**1 581 405**) és változó településen dolgozók (**269 628**) eltérő kategóriák. A tavaszi **megye–megye aggregált mátrix** ezeket egyesíti; a KSH **731 438** más vármegyei kapcsolata **nem azonos** a kizárólag „más magyar településen dolgozó” kategórián belüli, más megyébe ingázó **613 143** dolgozóval. A „napi ingázó” kifejezést ezért nem célszerű automatikusan az összes OD-kapcsolatra használni.
- A **külföldön dolgozó 122 581 főt** a nyári gazdasági aktivitási lépések kezelik külön; nincs belekényszerítve ebbe a tavaszi fizikai céges kiosztásba.
- A 10 628 kiosztatlan ágens a tavaszi **4 668 639** és **4 658 011** közötti összlétszám-különbség. Később a nyári belföldi létszámra újra kell ellenőrizni a kapacitásmérleget.
- Az új céges `company_size` értékek **modellkalibrációs becslések**, nem telephelyenként megfigyelt dolgozói létszámok. A cégméret-kategóriákat megtartottuk, a települések térbeli eloszlását nem változtattuk meg.
- A V3.3 kimenetét a nyári dolgozókhoz csatlakoztatva az **OD-arányok újra torzulhatnak**, ezért a nyári összerendelés után ismét kell megyei és települési validáció; nem szabad a korábbi, régi tavaszi `agents_with_workplaces.csv`-hez visszanyúlni.

## 6. A reprodukáláshoz megtartandó fő fájlok

**KSH és referencia:** `build_commuting_matrix_v2.py`; `04_commuting_matrix_v2_all_domestic.csv`; `09_commuting_category_probabilities_v2.csv`; `10_commuter_destinations_v2.csv` (az utóbbi kettő különösen a nyári településtípus- és ingázásikategória-kiosztáshoz).

**Cégkalibráció:** `run_generation_calibrated.py`; `generated_companies_calibrated.csv`; `recalibrate_company_sizes_by_county.py`; `generated_companies_county_calibrated_v2.csv`; `01_county_targets.csv`; `02_teaor_comparison.csv`; `03_county_teaor_bin_comparison.csv`; `04_recalibration_report.txt`.

**Kiosztás:** `assign_agents_to_workplaces_v3.py`; `assign_agents_to_workplaces_v31.py`; `assign_agents_to_workplaces_v32.py`; **`assign_agents_to_workplaces_v33.py`**; **`agents_with_workplaces_v33.csv`**; **`workplace_assignment_v33_report.txt`**; **`workplace_counties_v33.csv`**; **`workplace_od_v33_vs_ksh.csv`**.

## 7. Javasolt szakdolgozati felépítés (később kidolgozandó)

1. **Data and reference correction:** KSH beolvasás, lakóhely és munkahely oszlopok iránya, ingázási kategóriák.
2. **Workplace capacity recalibration:** kezdeti megyei kapacitástorzulás, országos/megyei célok, vállalatméret-korlátok, optimalizálási módszer, kompromisszum a TEÁOR-célokkal.
3. **Commuting-constrained agent assignment:** megyei OD-terv, saját megyei kvóták, kapacitáskorlátok, KSH-kapcsolatok védelme, TEÁOR-fallback, 10 628 kiosztatlan dolgozó elosztása.
4. **Results and limitations:** V3–V3.3 számszerű összehasonlítása; 20 vármegyei arány; TV-eltérés; kiugró OD-kapcsolatok; kalibráció és független validáció különválasztása; továbblépés a nyári teljes populációhoz.

**Későbbi folytatási mondat:** „A PanSim tavaszi munkahelykiosztás V3.3-nál tartunk. Ebből a riportból készítsd el a szakdolgozat angol *Recalibrated Workplace Capacities and Commuting-Constrained Agent Assignment* alfejezetét, a módszertan és az eredmények szétválasztásával, majd kösd hozzá a nyári populációs pipeline-hoz.”
