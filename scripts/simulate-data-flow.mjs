import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const GENERATED_DIR = path.join(ROOT, "data", "generated");
const DOCS_DIR = path.join(ROOT, "docs");
const FRONTEND_DATA = path.join(ROOT, "frontend", "src", "lib", "pilot-evidence-data.ts");

const INGEST_CONFIGS = [
  { file: "backend/ingest/us_city_permits.py", family: "permit_socrata", label: "Socrata permits" },
  { file: "backend/ingest/us_city_permits_arcgis.py", family: "permit_arcgis", label: "ArcGIS permits" },
  { file: "backend/ingest/us_city_permits_ckan.py", family: "permit_ckan", label: "CKAN permits" },
];

const LOCAL_CHICAGO_SOURCES = [
  ["backend/ingest/building_permits.py", "Chicago building permits"],
  ["backend/ingest/street_closures.py", "Chicago street closures"],
  ["backend/ingest/chicago_311_requests.py", "Chicago 311 requests"],
  ["backend/ingest/chicago_special_events.py", "Chicago special events"],
  ["backend/ingest/chicago_traffic_crashes.py", "Chicago traffic crashes"],
  ["backend/ingest/cta_alerts.py", "CTA alerts"],
  ["backend/ingest/idot_road_projects.py", "IDOT road projects"],
  ["backend/ingest/cook_county_permits.py", "Cook County permits"],
];

const CITY_ALIASES = {
  "Nyc": "New York",
  "New York City": "New York",
  "New York City Street Closures": "New York",
  "Mckinney": "McKinney",
  "Sf": "San Francisco",
  "Dc": "Washington DC",
  "St Louis": "St. Louis",
  "St Paul": "St. Paul",
  "Fort Worth": "Fort Worth",
  "Fort Wayne": "Fort Wayne",
  "San Antonio": "San Antonio",
  "San Diego": "San Diego",
  "San Francisco": "San Francisco",
  "San Jose": "San Jose",
  "El Paso": "El Paso",
  "Las Vegas": "Las Vegas",
  "Los Angeles": "Los Angeles",
  "New Orleans": "New Orleans",
  "Oklahoma City": "Oklahoma City",
  "Kansas City": "Kansas City",
  "Colorado Springs": "Colorado Springs",
  "Cedar Park": "Cedar Park",
  "Cape Coral": "Cape Coral",
  "Long Beach": "Long Beach",
  "North Port": "North Port",
  "Round Rock": "Round Rock",
  "Virginia Beach": "Virginia Beach",
  "Winston Salem": "Winston-Salem",
  "St Petersburg": "St. Petersburg",
  "Green Bay": "Green Bay",
};

const SOURCE_RECORD_MULTIPLIER = {
  permit_socrata: 5,
  permit_arcgis: 5,
  permit_ckan: 4,
  crime_trend: 3,
  local_chicago: 6,
};

const CUSTOMER_SEGMENTS = [
  {
    name: "CRE Due Diligence",
    buyer: "Acquisitions analyst or asset manager",
    paidOffer: "Portfolio disruption brief for deal memos and tour planning",
    monthlyPrice: 299,
    valueMetric: "Analyst hours and missed red flags avoided",
    valuePerAvoidedEvent: 1800,
  },
  {
    name: "Logistics Dispatch",
    buyer: "Urban operations or routing lead",
    paidOffer: "Route-risk API with weekly stop-risk export",
    monthlyPrice: 799,
    valueMetric: "Failed stops and rescheduled dispatches avoided",
    valuePerAvoidedEvent: 950,
  },
  {
    name: "Proptech Embed",
    buyer: "Marketplace or mapping product manager",
    paidOffer: "Embedded address intelligence API for listings and reports",
    monthlyPrice: 1500,
    valueMetric: "Engineering weeks and churn-risk questions avoided",
    valuePerAvoidedEvent: 2400,
  },
  {
    name: "Civic Coordination",
    buyer: "Infrastructure coordination or economic development lead",
    paidOffer: "Interagency disruption watchlist and public-impact brief",
    monthlyPrice: 2500,
    valueMetric: "Cross-agency conflicts identified before escalation",
    valuePerAvoidedEvent: 3200,
  },
];

function stableHash(input) {
  let hash = 2166136261;
  for (const char of input) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function boundedInt(seed, min, max) {
  return min + (stableHash(seed) % (max - min + 1));
}

function titleCase(value) {
  return value
    .replace(/_(tx|az|ca|nc|nj|or|mo)$/i, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase())
    .trim();
}

function normalizeCityName(cityName, cityState) {
  const source = cityState?.split(",")[0]?.trim() || cityName.trim();
  return CITY_ALIASES[source] || source;
}

function extractConfigBlocks(content) {
  const blocks = [];
  let index = content.indexOf("CITY_CONFIGS");
  if (index < 0) return blocks;
  index = content.indexOf("[", index);
  if (index < 0) return blocks;

  let depth = 0;
  let blockStart = -1;
  let inString = false;
  let quote = "";
  let escaped = false;

  for (let i = index; i < content.length; i += 1) {
    const char = content[i];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === quote) {
        inString = false;
      }
      continue;
    }
    if (char === '"' || char === "'") {
      inString = true;
      quote = char;
      continue;
    }
    if (char === "{") {
      if (depth === 0) blockStart = i;
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth === 0 && blockStart >= 0) {
        blocks.push(content.slice(blockStart, i + 1));
        blockStart = -1;
      }
    } else if (char === "]" && depth === 0) {
      break;
    }
  }

  return blocks;
}

function extractString(block, key) {
  const match = block.match(new RegExp(`["']${key}["']\\s*:\\s*["']([^"']+)["']`));
  return match?.[1] ?? null;
}

function addSource(cities, city, source) {
  if (!city) return;
  const normalized = normalizeCityName(city, source.cityState);
  const existing = cities.get(normalized) ?? { city: normalized, state: source.cityState?.split(",")[1]?.trim() ?? null, sources: [] };
  const key = `${source.family}:${source.sourceKey}`;
  if (!existing.sources.some((item) => `${item.family}:${item.sourceKey}` === key)) {
    existing.sources.push(source);
  }
  cities.set(normalized, existing);
}

function discoverConfiguredSources() {
  const cities = new Map();

  for (const config of INGEST_CONFIGS) {
    const fullPath = path.join(ROOT, config.file);
    const content = readFileSync(fullPath, "utf8");
    for (const block of extractConfigBlocks(content)) {
      const cityName = extractString(block, "city_name");
      const sourceKey = extractString(block, "source_key");
      const cityState = extractString(block, "city_state");
      if (!cityName || !sourceKey) continue;
      addSource(cities, cityName, {
        family: config.family,
        label: config.label,
        sourceKey,
        cityState,
      });
    }
  }

  const ingestDir = path.join(ROOT, "backend", "ingest");
  for (const fileName of readdirSync(ingestDir)) {
    if (!fileName.endsWith("_crime_trends.py")) continue;
    const sourceKey = fileName.replace(/\.py$/, "");
    const cityName = CITY_ALIASES[titleCase(sourceKey.replace(/_crime_trends$/, ""))] || titleCase(sourceKey.replace(/_crime_trends$/, ""));
    addSource(cities, cityName, {
      family: "crime_trend",
      label: "Crime trend ingest",
      sourceKey,
      cityState: null,
    });
  }

  for (const [relativePath, label] of LOCAL_CHICAGO_SOURCES) {
    const fullPath = path.join(ROOT, relativePath);
    try {
      readFileSync(fullPath, "utf8");
      addSource(cities, "Chicago", {
        family: "local_chicago",
        label,
        sourceKey: path.basename(relativePath, ".py"),
        cityState: "Chicago, IL",
      });
    } catch {
      // Ignore optional local sources that do not exist in a branch.
    }
  }

  return [...cities.values()].sort((a, b) => a.city.localeCompare(b.city));
}

function monthStart(index) {
  const date = new Date(Date.UTC(2026, 3 + index, 1));
  return date.toISOString().slice(0, 10);
}

function simulateCityMonth(city, source, monthIndex) {
  const max = SOURCE_RECORD_MULTIPLIER[source.family] ?? 3;
  const min = source.family === "crime_trend" ? 1 : 2;
  return boundedInt(`${city.city}:${source.sourceKey}:${monthIndex}`, min, max);
}

function disruptionScoreFor(city, monthIndex, generatedThisMonth) {
  const sourceCount = city.sources.length;
  const sourceFactor = Math.min(42, sourceCount * 2.2);
  const volumeFactor = Math.min(36, generatedThisMonth * 0.9);
  const seasonality = [3, 6, 9, 11, 8, 5, 4, 6, 7, 5, 3, 2][monthIndex % 12];
  const noise = boundedInt(`${city.city}:score:${monthIndex}`, -4, 5);
  return Math.max(8, Math.min(100, Math.round(16 + sourceFactor + volumeFactor + seasonality + noise)));
}

function buildSimulation(months) {
  const cities = discoverConfiguredSources();
  const sourceFlows = [];
  const citySummaries = [];
  const monthlyScores = [];

  for (const city of cities) {
    let generatedRecords = 0;
    let highRiskMonths = 0;
    let scoreTotal = 0;
    const cityMonthlyScores = [];

    for (let monthIndex = 0; monthIndex < months; monthIndex += 1) {
      const month = monthStart(monthIndex);
      let generatedThisMonth = 0;
      for (const source of city.sources) {
        const newRecords = simulateCityMonth(city, source, monthIndex);
        generatedThisMonth += newRecords;
        sourceFlows.push({
          city: city.city,
          month,
          source_family: source.family,
          source_key: source.sourceKey,
          source_label: source.label,
          new_records: newRecords,
        });
      }

      const disruptionScore = disruptionScoreFor(city, monthIndex, generatedThisMonth);
      cityMonthlyScores.push(disruptionScore);
      monthlyScores.push({
        city: city.city,
        month,
        disruption_score: disruptionScore,
        generated_records: generatedThisMonth,
        active_sources: city.sources.length,
      });
      generatedRecords += generatedThisMonth;
      scoreTotal += disruptionScore;
      if (disruptionScore >= 55) highRiskMonths += 1;
    }

    citySummaries.push({
      city: city.city,
      sources: city.sources.length,
      months,
      scenario_months: months,
      generated_records: generatedRecords,
      average_disruption_score: Number((scoreTotal / months).toFixed(1)),
      high_risk_months: highRiskMonths,
      source_families: [...new Set(city.sources.map((source) => source.family))].sort(),
      latest_month_score: cityMonthlyScores[cityMonthlyScores.length - 1],
    });
  }

  citySummaries.sort((a, b) => b.generated_records - a.generated_records || a.city.localeCompare(b.city));

  const totalGeneratedRecords = citySummaries.reduce((sum, city) => sum + city.generated_records, 0);
  const scenarioMonthCount = citySummaries.reduce((sum, city) => sum + city.scenario_months, 0);
  const sourceCount = cities.reduce((sum, city) => sum + city.sources.length, 0);
  const avoidableEvents = Math.max(24, Math.round(scenarioMonthCount * 0.18));

  const customerSegments = CUSTOMER_SEGMENTS.map((segment, index) => {
    const segmentEvents = Math.round(avoidableEvents * [0.7, 0.55, 0.45, 0.38][index]);
    const simulatedValue = segmentEvents * segment.valuePerAvoidedEvent;
    const sixMonthCost = segment.monthlyPrice * months;
    return {
      ...segment,
      avoidedEvents: segmentEvents,
      simulatedValue,
      sixMonthContractValue: sixMonthCost,
      valueToPrice: Number((simulatedValue / sixMonthCost).toFixed(2)),
      willingnessToPay: simulatedValue / sixMonthCost >= 3 ? "strong" : "needs proof",
    };
  });

  return {
    generated_at: new Date().toISOString(),
    months_simulated: months,
    city_count: citySummaries.length,
    source_count: sourceCount,
    generated_project_count: totalGeneratedRecords,
    scenario_month_count: scenarioMonthCount,
    city_summaries: citySummaries,
    source_flows: sourceFlows,
    monthly_scores: monthlyScores,
    customer_segments: customerSegments,
  };
}

function money(value) {
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

function writeSimulationDoc(simulation) {
  const lines = [
    "# Multi-Month Data Flow Simulation",
    "",
    `Generated: ${simulation.generated_at}`,
    "",
    `Months simulated: ${simulation.months_simulated}`,
    `Loaded cities simulated: ${simulation.city_count}`,
    `Configured city/source feeds simulated: ${simulation.source_count}`,
    `Generated synthetic source records: ${simulation.generated_project_count}`,
    `Scenario-month scores: ${simulation.scenario_month_count}`,
    "",
    "## City Summary",
    "",
    "| City | Sources | Months | Avg disruption score | High-risk months | Generated records | Source families |",
    "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ...simulation.city_summaries.map((city) => (
      `| ${city.city} | ${city.sources} | ${city.months} | ${city.average_disruption_score} | ${city.high_risk_months} | ${city.generated_records} | ${city.source_families.join(", ")} |`
    )),
    "",
    "## Customer Proposition Simulation",
    "",
    "| Segment | Buyer | Paid offer | Monthly price | Avoided events | Simulated value | Six-month contract | Value:price | WTP |",
    "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ...simulation.customer_segments.map((segment) => (
      `| ${segment.name} | ${segment.buyer} | ${segment.paidOffer} | ${money(segment.monthlyPrice)} | ${segment.avoidedEvents} | ${money(segment.simulatedValue)} | ${money(segment.sixMonthContractValue)} | ${segment.valueToPrice}x | ${segment.willingnessToPay} |`
    )),
    "",
    "## Product Implications",
    "",
    "- The sellable product is an evidence-backed disruption brief that updates as source feeds change, not a raw one-time score.",
    "- Buyer value improves when the app shows change over months, coverage depth by city, and practical actions tied to each segment.",
    "- The strongest paid wedge is CRE due diligence because the current pricing roadmap already supports a low-friction pilot and the buyer can use briefs immediately.",
    "- Logistics, proptech, and civic buyers require API/batch workflows, but the same city/source simulation proves why recurring monitoring is worth paying for.",
    "",
  ];
  writeFileSync(path.join(DOCS_DIR, "12_data_flow_simulation_results.md"), `${lines.join("\n")}\n`);
}

function writeFrontendData(simulation) {
  const existingPersonaPath = path.join(GENERATED_DIR, "persona_red_team_results.json");
  let personaAudit = null;
  try {
    personaAudit = JSON.parse(readFileSync(existingPersonaPath, "utf8")).summary;
  } catch {
    personaAudit = {
      persona_count: 0,
      result_count: 0,
      overall: 0,
      dimensions: {},
    };
  }

  const data = {
    generatedAt: simulation.generated_at,
    totals: {
      months: simulation.months_simulated,
      cities: simulation.city_count,
      sourceFeeds: simulation.source_count,
      generatedRecords: simulation.generated_project_count,
      scenarioMonths: simulation.scenario_month_count,
    },
    citySummaries: simulation.city_summaries,
    customerSegments: simulation.customer_segments,
    personaAudit,
  };

  writeFileSync(
    FRONTEND_DATA,
    `export const pilotEvidence = ${JSON.stringify(data, null, 2)} as const;\n`
  );
}

function main() {
  const monthsArg = process.argv.find((arg) => arg.startsWith("--months="));
  const months = monthsArg ? Number(monthsArg.split("=")[1]) : 6;
  if (!Number.isInteger(months) || months < 1 || months > 24) {
    throw new Error("--months must be an integer between 1 and 24");
  }

  mkdirSync(GENERATED_DIR, { recursive: true });
  mkdirSync(DOCS_DIR, { recursive: true });

  const simulation = buildSimulation(months);
  writeFileSync(path.join(GENERATED_DIR, "data_flow_simulation.json"), `${JSON.stringify(simulation, null, 2)}\n`);
  writeSimulationDoc(simulation);
  writeFrontendData(simulation);

  console.log(JSON.stringify({
    output: "docs/12_data_flow_simulation_results.md",
    data: "data/generated/data_flow_simulation.json",
    generated_project_count: simulation.generated_project_count,
    scenario_month_count: simulation.scenario_month_count,
    city_count: simulation.city_count,
    source_count: simulation.source_count,
  }, null, 2));
}

main();
