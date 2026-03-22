/**
 * Static Chicago street name list for client-side autocomplete prefix matching.
 *
 * Geocoders (Nominatim, Photon) are designed for complete-address lookup, not
 * real-time partial-name autocomplete. Typing "679 North Pe" returns Michigan,
 * Milwaukee, etc. because the geocoder doesn't know "Pe" means Peoria.
 *
 * This list covers the most commonly searched Chicago streets. When the user
 * types a partial street name we match against this list and construct complete
 * candidate addresses, then return those to the autocomplete dropdown.
 *
 * To add streets: append to STREETS as [name, suffix] pairs.
 */

type StreetEntry = [name: string, suffix: string];

// ---------------------------------------------------------------------------
// Street data — roughly sorted by area then name
// ---------------------------------------------------------------------------
const STREETS: StreetEntry[] = [
  // Major diagonals / named roads
  ["Archer", "Avenue"],
  ["Blue Island", "Avenue"],
  ["Lincoln", "Avenue"],
  ["Milwaukee", "Avenue"],
  ["Ogden", "Avenue"],
  ["Wacker", "Drive"],
  ["Lake Shore", "Drive"],

  // East–West (typically W or E prefix)
  ["Adams", "Street"],
  ["Armitage", "Avenue"],
  ["Augusta", "Boulevard"],
  ["Barry", "Avenue"],
  ["Belmont", "Avenue"],
  ["Berwyn", "Avenue"],
  ["Bloomingdale", "Avenue"],
  ["Bryn Mawr", "Avenue"],
  ["Carroll", "Avenue"],
  ["Catalpa", "Avenue"],
  ["Cermak", "Road"],
  ["Chicago", "Avenue"],
  ["Cortland", "Street"],
  ["Congress", "Parkway"],
  ["Devon", "Avenue"],
  ["Dickens", "Avenue"],
  ["Division", "Street"],
  ["Diversey", "Parkway"],
  ["Erie", "Street"],
  ["Farwell", "Avenue"],
  ["Fillmore", "Street"],
  ["Fullerton", "Avenue"],
  ["Garfield", "Boulevard"],
  ["Grace", "Street"],
  ["Grand", "Avenue"],
  ["Granville", "Avenue"],
  ["Harrison", "Street"],
  ["Hirsch", "Street"],
  ["Howard", "Street"],
  ["Huron", "Street"],
  ["Iowa", "Street"],
  ["Irving Park", "Road"],
  ["Jackson", "Boulevard"],
  ["Jarvis", "Avenue"],
  ["Kinzie", "Street"],
  ["Lawrence", "Avenue"],
  ["Lexington", "Street"],
  ["Madison", "Street"],
  ["Marquette", "Road"],
  ["Monroe", "Street"],
  ["Montrose", "Avenue"],
  ["Morse", "Avenue"],
  ["Nelson", "Street"],
  ["North", "Avenue"],
  ["Ohio", "Street"],
  ["Ontario", "Street"],
  ["Pershing", "Road"],
  ["Peterson", "Avenue"],
  ["Polk", "Street"],
  ["Pratt", "Boulevard"],
  ["Randolph", "Street"],
  ["Roosevelt", "Road"],
  ["Roscoe", "Street"],
  ["Sunnyside", "Avenue"],
  ["Superior", "Street"],
  ["Taylor", "Street"],
  ["Thomas", "Street"],
  ["Thorndale", "Avenue"],
  ["Touhy", "Avenue"],
  ["Van Buren", "Street"],
  ["Washington", "Street"],
  ["Webster", "Avenue"],
  ["Wellington", "Avenue"],
  ["Wilson", "Avenue"],

  // North–South (typically N or S prefix)
  ["Aberdeen", "Street"],
  ["Ashland", "Avenue"],
  ["Austin", "Boulevard"],
  ["Bell", "Avenue"],
  ["California", "Avenue"],
  ["Calumet", "Avenue"],
  ["Carpenter", "Street"],
  ["Central", "Avenue"],
  ["Cicero", "Avenue"],
  ["Clark", "Street"],
  ["Clinton", "Street"],
  ["Cottage Grove", "Avenue"],
  ["Damen", "Avenue"],
  ["Dearborn", "Street"],
  ["Desplaines", "Street"],
  ["Emerald", "Avenue"],
  ["Franklin", "Street"],
  ["Green", "Street"],
  ["Halsted", "Street"],
  ["Harlem", "Avenue"],
  ["Hamilton", "Avenue"],
  ["Hermitage", "Avenue"],
  ["Honore", "Street"],
  ["Hoyne", "Avenue"],
  ["Indiana", "Avenue"],
  ["Jefferson", "Street"],
  ["Kedzie", "Avenue"],
  ["King Drive", ""],
  ["Kostner", "Avenue"],
  ["Laflin", "Street"],
  ["LaSalle", "Street"],
  ["Laramie", "Avenue"],
  ["Leavitt", "Street"],
  ["Loomis", "Street"],
  ["Marshfield", "Avenue"],
  ["May", "Street"],
  ["Michigan", "Avenue"],
  ["Morgan", "Street"],
  ["Narragansett", "Avenue"],
  ["Oakley", "Avenue"],
  ["Oak Park", "Avenue"],
  ["Paulina", "Street"],
  ["Peoria", "Street"],
  ["Prairie", "Avenue"],
  ["Pulaski", "Road"],
  ["Racine", "Avenue"],
  ["Sacramento", "Boulevard"],
  ["Sangamon", "Street"],
  ["Seeley", "Avenue"],
  ["Spaulding", "Avenue"],
  ["St Louis", "Avenue"],
  ["State", "Street"],
  ["Stony Island", "Avenue"],
  ["Throop", "Street"],
  ["Vincennes", "Avenue"],
  ["Wabash", "Avenue"],
  ["Wells", "Street"],
  ["Wentworth", "Avenue"],
  ["Western", "Avenue"],
  ["Winchester", "Avenue"],
  ["Wolcott", "Avenue"],
  ["Wood", "Street"],
];

// Direction words used in Chicago addresses, keyed lowercase → display form.
const DIRECTIONS: Record<string, string> = {
  north: "North",
  south: "South",
  east: "East",
  west: "West",
  n: "North",
  s: "South",
  e: "East",
  w: "West",
};

/**
 * Suggest Chicago addresses from the static street list given a partial query.
 *
 * Returns up to 5 full addresses like "679 North Peoria Street, Chicago, IL"
 * when the query contains at least a partial street name. Returns [] when the
 * query has fewer than 2 characters of street name (not enough to be useful).
 */
export function suggestFromStaticList(query: string): string[] {
  const raw = query.trim();
  if (!raw) return [];

  // Pull house number from the front of the query.
  const houseMatch = raw.match(/^(\d+)\s*/);
  const house = houseMatch ? houseMatch[1] : "";
  let rest = house ? raw.slice(houseMatch![0].length) : raw;

  // Pull direction word if present.
  let dirDisplay = "";
  const dirMatch = rest.match(/^(north|south|east|west|n\.?|s\.?|e\.?|w\.?)\s+/i);
  if (dirMatch) {
    const key = dirMatch[1].replace(/\.$/, "").toLowerCase();
    dirDisplay = DIRECTIONS[key] ?? "";
    rest = rest.slice(dirMatch[0].length);
  }

  // What remains is the partial street name. Require at least 2 chars.
  const frag = rest.trim().toLowerCase();
  if (frag.length < 2) return [];

  const results: string[] = [];
  for (const [name, suffix] of STREETS) {
    if (!name.toLowerCase().startsWith(frag)) continue;
    const streetPart = suffix ? `${name} ${suffix}` : name;
    const parts: string[] = [];
    if (house) parts.push(house);
    if (dirDisplay) parts.push(dirDisplay);
    parts.push(streetPart);
    parts.push("Chicago, IL");
    results.push(parts.join(" "));
    if (results.length >= 5) break;
  }
  return results;
}
