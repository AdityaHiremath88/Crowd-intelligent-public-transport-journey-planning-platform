# Routing algorithm comparison

| Algorithm | Strength | Cost / issue | CrowdWise decision |
|---|---|---|---|
| Time-dependent Dijkstra | Familiar graph search, naturally handles transfer edges and departure times | Needs a careful timetable/transfer graph; multicriteria labels and timetable waiting can increase state; easy to mis-model staying aboard | Not selected as primary. Could be a reference implementation for a tiny network. |
| Connection Scan Algorithm (CSA) | Simple scan over time-ordered connections; effective for timetable earliest-arrival routing | Multi-criteria and route/transfer constraints need extensions; connection dataset/indexing required | Strong alternative if feed import stores connection rows and tests show a fit. |
| RAPTOR | Uses route/trip timetable structure, rounds correspond to boarding count, computes arrival/transfer Pareto tradeoffs; paper reports efficient route scans without graph preprocessing | Requires route patterns and trips grouped consistently; multi-criteria crowd extension requires multiple labels and careful dominance | Research target for larger real feed and crowdedness criteria. Primary reference: [Delling, Pajor & Werneck 2015](https://pubsonline.informs.org/doi/10.1287/trsc.2014.0534). |
| OpenTripPlanner | Mature multimodal system with GTFS, street network and transfer integration | A larger Java service and operational complexity; crowd integration needs extension/API work | Not adopted for current modular Python prototype; reconsider if walking and multimodal routing become required. |
| Current bounded label expansion | Small Python implementation directly over trip events; round/transfer semantics are understandable and testable | One earliest label per stop/round, no feet paths/transfers file/frequencies, may scan many departures; not equivalent to fully optimized RAPTOR | Keep for hackathon-scale direct/bounded journeys only, benchmark before claiming network-scale performance. |

Algorithm sources: original [RAPTOR research](https://pubsonline.informs.org/doi/10.1287/trsc.2014.0534), [GTFS Schedule](https://gtfs.org/documentation/schedule/reference/) and [OpenTripPlanner](https://www.opentripplanner.org/). Selection should be revisited only with a feed and measured query workload; no complexity narrative replaces actual benchmarks.


