console.error('web/scripts/seed.ts has been deprecated.');
console.error('Use the Python import pipeline under scripts/db/ instead.');
console.error('Suggested order: init_database.py -> import_sub_event_type.py -> import_event_categories.py -> import_players.py -> import_rankings.py -> import_events.py -> import_matches.py -> import_event_draw_matches.py -> import_sub_events.py');
process.exit(1);
