# Event Draw Classification Review

Generated: 2026-04-22T18:33:49

## Summary

- Unsupported Main Draw round groups not included in event_draw_matches: 28
- Final rows reclassified as Bronze: 1
- Raw Final vs draw Final audit groups: 1
- Bronze rows in event_draw_matches: 57

## Draw Round Distribution

| Draw round | Count |
|---|---:|
| R256 | 19 |
| R128 | 1123 |
| R64 | 2770 |
| R32 | 2813 |
| R16 | 2373 |
| QuarterFinal | 1959 |
| SemiFinal | 1047 |
| Bronze | 57 |
| Final | 578 |

## Unsupported Main Draw Round Groups

These rows remain excluded because their round cannot be reliably mapped into a bracket round. Most are team-event rows with empty round values.

| event_id | Event | Sub-event | Stage | Round | Count |
|---:|---|---|---|---|---:|
| 255 | ITTF European Table Tennis Championships Ekaterinburg 2015 | MT | Main Draw |  | 233 |
| 508 | ITTF European Team Championships Luxembourg 2017 | MT | Main Draw |  | 224 |
| 303 | European Team Table Tennis Championships Lisbon 2014 | MT | Main Draw |  | 222 |
| 303 | European Team Table Tennis Championships Lisbon 2014 | WT | Main Draw |  | 194 |
| 508 | ITTF European Team Championships Luxembourg 2017 | WT | Main Draw |  | 188 |
| 254 | ITTF Asian Championships Pattaya 2015 | MT | Main Draw |  | 178 |
| 255 | ITTF European Table Tennis Championships Ekaterinburg 2015 | WT | Main Draw |  | 171 |
| 515 | ITTF Asian Championships Wuxi 2017 | MT | Main Draw |  | 145 |
| 254 | ITTF Asian Championships Pattaya 2015 | WT | Main Draw |  | 121 |
| 515 | ITTF Asian Championships Wuxi 2017 | WT | Main Draw |  | 117 |
| 250 | 11th African Games Brazzaville 2015 | MT | Main Draw |  | 89 |
| 250 | 11th African Games Brazzaville 2015 | WT | Main Draw |  | 71 |
| 203 | ITTF Africa Senior Championships Cairo 2015 | MT | Main Draw |  | 62 |
| 380 | ITTF Africa Senior Championships Agadir 2016 | MT | Main Draw |  | 61 |
| 226 | 1st European Games Baku 2015 | WT | Main Draw |  | 45 |
| 858 | ITTF Pan American Championships Cartagena de Indias 2017 | MT | Main Draw |  | 43 |
| 226 | 1st European Games Baku 2015 | MT | Main Draw |  | 42 |
| 858 | ITTF Pan American Championships Cartagena de Indias 2017 | WT | Main Draw |  | 42 |
| 205 | Team World Cup Dubai 2015 | WT | Main Draw |  | 25 |
| 203 | ITTF Africa Senior Championships Cairo 2015 | WT | Main Draw |  | 24 |
| 205 | Team World Cup Dubai 2015 | MT | Main Draw |  | 24 |
| 235 | XVII Pan American Games Toronto 2015 | MT | Main Draw |  | 23 |
| 235 | XVII Pan American Games Toronto 2015 | WT | Main Draw |  | 23 |
| 380 | ITTF Africa Senior Championships Agadir 2016 | WT | Main Draw |  | 16 |
| 165 | ITTF Oceania Championships Bendigo 2016 | MT | Main Draw |  | 5 |
| 165 | ITTF Oceania Championships Bendigo 2016 | U21MT | Main Draw |  | 3 |
| 165 | ITTF Oceania Championships Bendigo 2016 | U21WT | Main Draw |  | 3 |
| 165 | ITTF Oceania Championships Bendigo 2016 | WT | Main Draw |  | 3 |

## Final Reclassification Audit

These raw `Main Draw / Final` rows were intentionally displayed as `Bronze` because both sides matched the SemiFinal losers.

| event_id | Event | Sub-event | match_id | Score | Side A | Side B | Note |
|---:|---|---|---:|---|---|---|---|
| 250 | 11th African Games Brazzaville 2015 | MS | 102 | 4-3 | `wang jianan|cgo` | `assar khalid|egy` | Final row reclassified because sides are semifinal losers |

## Raw Final vs Draw Final Audit

| event_id | Event | Sub-event | Raw Final Count | Draw Final Count |
|---:|---|---|---:|---:|
| 250 | 11th African Games Brazzaville 2015 | MS | 2 | 1 |

## Bronze Rows

| event_id | Event | Sub-event | match_id | Source | Verified | Score | Side A | Side B |
|---:|---|---|---:|---|---:|---|---|---|
| 165 | ITTF Oceania Championships Bendigo 2016 | MS | 17893 | position_draw_round2 | 1 | 2-4 | `hu heming|aus` | `liu tengteng|nzl` |
| 165 | ITTF Oceania Championships Bendigo 2016 | WS | 17905 | position_draw_round2 | 1 | 0-4 | `dederko zhenhua|aus` | `zhang ziyu|aus` |
| 226 | 1st European Games Baku 2015 | MS | 677 | position_draw_round2 | 1 | 2-4 | `drinkhall paul|eng` | `kou lei|ukr` |
| 226 | 1st European Games Baku 2015 | WS | 675 | position_draw_round2 | 1 | 1-4 | `odorova eva|svk` | `hu melek|tur` |
| 250 | 11th African Games Brazzaville 2015 | MS | 102 | final_reclassified | 1 | 4-3 | `wang jianan|cgo` | `assar khalid|egy` |
| 250 | 11th African Games Brazzaville 2015 | WS | 127 | position_draw_round2 | 1 | 4-1 | `han xing|cgo` | `oshonaike olufunke|ngr` |
| 315 | Men's World Cup Halmstad 2015 | MS | 23704 | position_draw_round2 | 1 | 4-2 | `ovtcharov dimitrij|ger` | `mizutani jun|jpn` |
| 316 | Women's World Cup Sendai 2015 | WS | 26676 | position_draw_round2 | 1 | 4-2 | `solja petrissa|ger` | `li jiao|ned` |
| 328 | Men's World Cup Dusseldorf 2014 | MS | 23676 | position_draw_round2 | 1 | 2-4 | `mizutani jun|jpn` | `boll timo|ger` |
| 329 | Women's World Cup Linz 2014 | WS | 26596 | position_draw_round2 | 1 | 4-3 | `ishikawa kasumi|jpn` | `pota georgina|hun` |
| 374 | Men's World Cup Saarbrucken 2016 | MS | 23748 | position_draw_round2 | 1 | 1-4 | `karlsson kristian|swe` | `wong chun ting|hkg` |
| 375 | Women's World Cup Philadelphia 2016 | WS | 26640 | position_draw_round2 | 1 | 4-1 | `feng tianwei|sgp` | `tie yana|hkg` |
| 506 | Men's World Cup Liege 2017 | MS | 3236 | position_draw_round2 | 1 | 4-2 | `ma long|chn` | `gauzy simon|fra` |
| 507 | Women's World Cup Markham 2017 | WS | 26623 | position_draw_round2 | 1 | 4-2 | `cheng i-ching|tpe` | `hirano miu|jpn` |
| 894 | Women's World Cup Chengdu 2018 | WS | 26539 | position_draw_round2 | 1 | 4-1 | `cheng i-ching|tpe` | `ishikawa kasumi|jpn` |
| 895 | Men's World Cup Paris 2018 | MS | 23731 | position_draw_round2 | 1 | 4-1 | `lin gaoyuan|chn` | `ovtcharov dimitrij|ger` |
| 2005 | European Games Minsk 2019 | MS | 4629 | position_draw_round2 | 1 | 4-1 | `pucar tomislav|cro` | `kou lei|ukr` |
| 2005 | European Games Minsk 2019 | WS | 4628 | position_draw_round2 | 1 | 4-2 | `ni xia lian|lux` | `yang xiaoxin|mon` |
| 2005 | European Games Minsk 2019 | XD | 4622 | position_draw_round2 | 1 | 1-3 | `pistej lubomir|svk||varady barbora|svk` | `flore tristan|fra||gasnier laura|fra` |
| 2009 | ITTF Africa Cup Lagos 2019 | MS | 8374 | position_draw_round2 | 1 | 3-0 | `aruna quadri|ngr` | `kherouf sami|alg` |
| 2009 | ITTF Africa Cup Lagos 2019 | WS | 8368 | position_draw_round2 | 1 | 3-2 | `edem offiong|ngr` | `garci fadwa|tun` |
| 2012 | All Africa Games Rabat 2019 | MT | 1396 | position_draw_round2 | 1 | 0-3 | `lignandzi michel|cgo` | `hmam adam|tun` |
| 2012 | All Africa Games Rabat 2019 | WT | 1378 | position_draw_round2 | 1 | 1-3 | `kessaci katia|alg` | `garci fadwa|tun` |
| 2014 | Women's World Cup Chengdu 2019 | WS | 26567 | position_draw_round2 | 1 | 4-1 | `feng tianwei|sgp` | `zhang lily|usa` |
| 2015 | Men's World Cup Chengdu 2019 | MS | 23647 | position_draw_round2 | 1 | 4-3 | `lin yun-ju|tpe` | `ma long|chn` |
| 2092 | ITTF Asian Championships Yogyakarta 2019 | MT | 12549 | position_draw_round2 | 1 | 3-1 | `an ji song|prk` | `panagitgun yanapong|tha` |
| 2092 | ITTF Asian Championships Yogyakarta 2019 | MT | 12550 | position_draw_round2 | 1 | 3-2 | `ham yu song|prk` | `wisutmaythangkoon supanut|tha` |
| 2092 | ITTF Asian Championships Yogyakarta 2019 | WT | 12598 | position_draw_round2 | 1 | 1-3 | `lyne karen|mas` | `batra manika|ind` |
| 2092 | ITTF Asian Championships Yogyakarta 2019 | WT | 12600 | position_draw_round2 | 1 | 1-3 | `tee ai xin|mas` | `kamath archana|ind` |
| 2263 | Dishang 2020 ITTF Women’s World Cup Weihai 2020 | WS | 3208 | position_draw_round2 | 1 | 0-4 | `han ying|ger` | `ito mima|jpn` |
| 2265 | Dishang 2020 ITTF Men’s World Cup Weihai 2020 | MS | 3177 | position_draw_round2 | 1 | 3-4 | `jang woojin|kor` | `harimoto tomokazu|jpn` |
| 2473 | ITTF African Championships Yaounde 2021 | MT | 9897 | position_draw_round2 | 1 | 3-1 | `kherouf sami|alg` | `agbetoglo mawussi|tog` |
| 2473 | ITTF African Championships Yaounde 2021 | MT | 9898 | position_draw_round2 | 1 | 3-2 | `bouriah larbi|alg` | `fanny kokou|tog` |
| 2473 | ITTF African Championships Yaounde 2021 | WT | 9894 | position_draw_round2 | 1 | 3-1 | `garci fadwa|tun` | `hosenally oumehani|mri` |
| 2473 | ITTF African Championships Yaounde 2021 | WT | 9895 | position_draw_round2 | 1 | 3-1 | `zoghlami maram|tun` | `jalim nandeshwaree|mri` |
| 2473 | ITTF African Championships Yaounde 2021 | WT | 9896 | position_draw_round2 | 1 | 3-0 | `haj salah abir|tun` | `hosenally ashfani|mri` |
| 2576 | ITTF-Africa Cup Lagos 2022 | MS | 6811 | position_draw_round2 | 1 | 1-3 | `saleh ahmed|egy` | `elbeiali mohamed|egy` |
| 2576 | ITTF-Africa Cup Lagos 2022 | WS | 6810 | position_draw_round2 | 1 | 1-3 | `alhodaby mariam|egy` | `meshref dina|egy` |
| 2745 | ITTF-Africa Cup Nairobi 2023 | MS | 6933 | position_draw_round2 | 1 | 3-0 | `elbeiali mohamed|egy` | `razafinarivo antoine|mad` |
| 2745 | ITTF-Africa Cup Nairobi 2023 | WS | 6930 | position_draw_round2 | 1 | 3-1 | `alhodaby marwa|egy` | `hanffou sarah|cmr` |
| 2785 | European Games Krakow-Malopolska 2023 | MS | 4373 | position_draw_round2 | 1 | 4-0 | `lebrun alexis|fra` | `gacina andrej|cro` |
| 2785 | European Games Krakow-Malopolska 2023 | MT | 4505 | position_draw_round2 | 1 | 1-3 | `lebrun alexis|fra` | `apolonia tiago|por` |
| 2785 | European Games Krakow-Malopolska 2023 | WS | 4424 | position_draw_round2 | 1 | 4-3 | `samara elizabeta|rou` | `bajor natalia|pol` |
| 2785 | European Games Krakow-Malopolska 2023 | WT | 4501 | position_draw_round2 | 1 | 3-2 | `shao jieni|por` | `yuan jia nan|fra` |
| 2785 | European Games Krakow-Malopolska 2023 | WT | 4502 | position_draw_round2 | 1 | 3-1 | `yu fu|por` | `pavade prithika|fra` |
| 2785 | European Games Krakow-Malopolska 2023 | XD | 4315 | position_draw_round2 | 1 | 3-1 | `ionescu ovidiu|rou||szocs bernadette|rou` | `robles alvaro|esp||xiao maria|esp` |
| 2795 | ITTF-Oceania Championships Townsville 2023 | MT | 8100 | position_draw_round2 | 1 | 3-2 | `morisseau jerome|ncl` | `carnet bydhir|pyf` |
| 2795 | ITTF-Oceania Championships Townsville 2023 | MT | 8101 | position_draw_round2 | 1 | 0-3 | `dey jeremy|ncl` | `belrose ocean|pyf` |
| 2795 | ITTF-Oceania Championships Townsville 2023 | MT | 8102 | position_draw_round2 | 1 | 2-3 | `perrot adrien|ncl` | `pambrun arii|pyf` |
| 2795 | ITTF-Oceania Championships Townsville 2023 | MT | 8103 | position_draw_round2 | 1 | 1-3 | `morisseau jerome|ncl` | `belrose ocean|pyf` |
| 3122 | ITTF-ATTU Asian Cup Shenzhen 2025 | MS | 7191 | position_draw_round2 | 1 | 4-0 | `lin shidong|chn` | `lin yun-ju|tpe` |
| 3122 | ITTF-ATTU Asian Cup Shenzhen 2025 | WS | 7190 | position_draw_round2 | 1 | 0-4 | `chen xingtong|chn` | `kuai man|chn` |
| 3147 | ITTF-Oceania Championships Christchurch 2025 | MT | 7863 | position_draw_round2 | 1 | 3-2 | `utia angelo|pyf` | `dey jeremy|ncl` |
| 3147 | ITTF-Oceania Championships Christchurch 2025 | MT | 7864 | position_draw_round2 | 1 | 2-3 | `pambrun ariinui|pyf` | `morisseau jerome|ncl` |
| 3147 | ITTF-Oceania Championships Christchurch 2025 | MT | 7866 | position_draw_round2 | 1 | 0-3 | `utia angelo|pyf` | `morisseau jerome|ncl` |
| 3471 | ITTF-ATTU Asian Cup Haikou 2026 | MS | 7063 | position_draw_round2 | 1 | 1-4 | `chang yu-an|tpe` | `togami shunsuke|jpn` |
| 3471 | ITTF-ATTU Asian Cup Haikou 2026 | WS | 7062 | position_draw_round2 | 1 | 4-1 | `kuai man|chn` | `harimoto miwa|jpn` |
