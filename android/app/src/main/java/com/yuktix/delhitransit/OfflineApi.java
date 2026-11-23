package com.yuktix.delhitransit;

import android.content.Context;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.webkit.JavascriptInterface;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Collections;
import java.util.Comparator;
import java.util.Date;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TimeZone;
import java.util.UUID;

/** Local, read-only API adapter for the offline Android package. */
public final class OfflineApi {
    private final File databaseFile;
    private final SharedPreferences reportStore;

    public OfflineApi(Context context, File databaseFile) {
        this.databaseFile = databaseFile;
        this.reportStore = context.getSharedPreferences("yuktix_community_reports", Context.MODE_PRIVATE);
    }

    @JavascriptInterface
    public String request(String path, String method, String body) {
        return requestWithToken(path, method, body, "");
    }

    @JavascriptInterface
    public String requestWithToken(String path, String method, String body, String clientToken) {
        SQLiteDatabase db = null;
        try {
            db = SQLiteDatabase.openDatabase(databaseFile.getAbsolutePath(), null, SQLiteDatabase.OPEN_READONLY);
            Object payload = dispatch(db, path == null ? "/" : path, method == null ? "GET" : method, body == null ? "" : body, clientToken == null ? "" : clientToken);
            return new JSONObject().put("ok", true).put("status", 200).put("payload", payload).toString();
        } catch (ApiError e) {
            try {
                JSONObject detail = new JSONObject().put("message", e.getMessage()).put("code", e.code);
                return new JSONObject().put("ok", false).put("status", e.status)
                        .put("payload", new JSONObject().put("detail", detail)).toString();
            } catch (Exception ignored) { return "{\"ok\":false,\"status\":500,\"payload\":{}}"; }
        } catch (Exception e) {
            try {
                JSONObject detail = new JSONObject().put("message", "Offline data could not answer this request.").put("code", "OFFLINE_QUERY_FAILED");
                return new JSONObject().put("ok", false).put("status", 500).put("payload", new JSONObject().put("detail", detail)).toString();
            } catch (Exception ignored) { return "{\"ok\":false,\"status\":500,\"payload\":{}}"; }
        } finally { if (db != null) db.close(); }
    }

    private Object dispatch(SQLiteDatabase db, String rawPath, String method, String body, String clientToken) throws Exception {
        String path = rawPath.split("\\?", 2)[0];
        Map<String, String> query = parseQuery(rawPath.contains("?") ? rawPath.substring(rawPath.indexOf('?') + 1) : "");
        if (path.equals("/health") || path.equals("/api/v2/health")) return new JSONObject().put("status", "ok").put("service", "yuktix-offline");
        if (path.equals("/api/v2/capabilities")) return new JSONObject().put("service", "yuktix-offline")
                .put("scheduled_journey_search", true).put("gtfs_stop_search", true)
                .put("historical_route_activity", true).put("estimated_fares", true)
                .put("physical_crowding_estimates", false).put("live_vehicle_tracking", false);
        if (path.equals("/api/v2/stops")) return stops(db, query.get("q"), number(query.get("limit"), 8));
        if (path.equals("/api/v2/routes")) return routes(db, query.get("q"), number(query.get("limit"), 12));
        if (path.startsWith("/api/v2/routes/") && path.endsWith("/activity")) {
            String id = path.substring("/api/v2/routes/".length(), path.length() - "/activity".length());
            return activity(db, decode(id), query);
        }
        if (path.startsWith("/api/v2/routes/")) return routeDetail(db, decode(path.substring("/api/v2/routes/".length())));
        if (path.equals("/api/v2/journeys/search") && method.equalsIgnoreCase("POST")) return journeySearch(db, new JSONObject(body));
        if (path.startsWith("/api/v2/crowding/stop/")) return localCrowd(db, decode(path.substring("/api/v2/crowding/stop/".length())));
        if (path.startsWith("/api/v2/reports/stop/")) return localReports(db, decode(path.substring("/api/v2/reports/stop/".length())));
        if ((path.equals("/api/v2/reports/crowd") || path.equals("/api/v1/reports/crowd")) && method.equalsIgnoreCase("POST")) return saveReport(db, new JSONObject(body), clientToken);
        if (path.equals("/api/v1/analytics/overview")) return overview(db);
        if (path.startsWith("/api/v1/analytics/trends")) return trends(db);
        if (path.startsWith("/api/v1/analytics/corridors")) return corridors(db, number(query.get("limit"), 8));
        if (path.equals("/api/v2/reports/crowd") || path.equals("/api/v1/reports/crowd")) throw new ApiError(405, "METHOD_NOT_ALLOWED", "Crowd reports must be submitted with POST.");
        throw new ApiError(404, "NOT_FOUND", "This feature is not available in the offline app.");
    }

    private JSONObject stops(SQLiteDatabase db, String query, int limit) throws Exception {
        String q = query == null ? "" : query.trim();
        if (q.length() < 2) return new JSONObject().put("items", new JSONArray()).put("source", "Bundled Delhi GTFS schedule").put("offset", 0).put("total_returned", 0).put("next_offset", JSONObject.NULL);
        JSONArray items = new JSONArray();
        Cursor c = db.rawQuery("SELECT stop_id,coalesce(stop_name,stop_id),stop_lat,stop_lon FROM stops WHERE lower(stop_name) LIKE ? OR lower(stop_id)=? ORDER BY CASE WHEN lower(stop_name)=? THEN 0 WHEN lower(stop_name) LIKE ? THEN 1 ELSE 2 END,lower(stop_name),stop_id LIMIT ?",
                new String[]{"%" + q.toLowerCase(Locale.ROOT) + "%", q.toLowerCase(Locale.ROOT), q.toLowerCase(Locale.ROOT), q.toLowerCase(Locale.ROOT) + "%", String.valueOf(clamp(limit, 1, 50))});
        while (c.moveToNext()) items.put(stopJson(c));
        c.close();
        return new JSONObject().put("items", items).put("source", "Bundled Delhi GTFS schedule").put("offset", 0).put("total_returned", items.length()).put("next_offset", JSONObject.NULL);
    }

    private JSONObject stopJson(Cursor c) throws Exception {
        return new JSONObject().put("stop_id", c.getString(0)).put("stop_name", c.getString(1))
                .put("latitude", c.isNull(2) ? JSONObject.NULL : c.getDouble(2))
                .put("longitude", c.isNull(3) ? JSONObject.NULL : c.getDouble(3))
                .put("coordinate_source", "gtfs_publisher_unverified");
    }

    private JSONObject routes(SQLiteDatabase db, String query, int limit) throws Exception {
        String q = query == null ? "" : query.trim();
        if (q.isEmpty()) return new JSONObject().put("items", new JSONArray()).put("source", "Bundled Delhi GTFS schedule");
        JSONArray items = new JSONArray();
        Cursor c = db.rawQuery("SELECT r.route_id,coalesce(nullif(r.route_short_name,''),nullif(r.route_long_name,''),r.route_id),coalesce(r.route_long_name,''),(SELECT count(*) FROM trips t WHERE t.route_id=r.route_id) FROM routes r WHERE lower(coalesce(r.route_short_name,'')) LIKE ? OR lower(coalesce(r.route_long_name,'')) LIKE ? ORDER BY CASE WHEN lower(coalesce(r.route_short_name,''))=? THEN 0 WHEN lower(coalesce(r.route_short_name,'')) LIKE ? THEN 1 ELSE 2 END,lower(coalesce(r.route_short_name,'')),r.route_id LIMIT ?",
                new String[]{"%" + q.toLowerCase(Locale.ROOT) + "%", "%" + q.toLowerCase(Locale.ROOT) + "%", q.toLowerCase(Locale.ROOT), q.toLowerCase(Locale.ROOT) + "%", String.valueOf(clamp(limit, 1, 50))});
        while (c.moveToNext()) items.put(new JSONObject().put("route_id", c.getString(0)).put("route_name", c.getString(1)).put("route_long_name", c.getString(2)).put("scheduled_trip_count", c.getInt(3)));
        c.close();
        return new JSONObject().put("items", items).put("source", "Bundled Delhi GTFS schedule");
    }

    private JSONObject routeDetail(SQLiteDatabase db, String routeId) throws Exception {
        Cursor route = db.rawQuery("SELECT route_id,coalesce(nullif(route_short_name,''),route_id),coalesce(route_long_name,'') FROM routes WHERE route_id=?", new String[]{routeId});
        if (!route.moveToFirst()) { route.close(); throw new ApiError(404, "UNKNOWN_ROUTE", "That route is not in the bundled schedule."); }
        String id = route.getString(0), name = route.getString(1), longName = route.getString(2); route.close();
        Cursor trip = db.rawQuery("SELECT t.trip_id,coalesce(t.trip_headsign,''),count(*) n FROM trips t JOIN stop_times s USING(trip_id) WHERE t.route_id=? GROUP BY t.trip_id,t.trip_headsign ORDER BY n DESC,t.trip_id LIMIT 1", new String[]{routeId});
        if (!trip.moveToFirst()) { trip.close(); throw new ApiError(404, "ROUTE_WITHOUT_TRIPS", "No trips were found for this route."); }
        String tripId = trip.getString(0), headsign = trip.getString(1); trip.close();
        JSONArray stops = new JSONArray();
        Cursor c = db.rawQuery("SELECT s.stop_id,coalesce(s.stop_name,s.stop_id) FROM stop_times st JOIN stops s USING(stop_id) WHERE st.trip_id=? ORDER BY st.stop_sequence", new String[]{tripId});
        while (c.moveToNext()) stops.put(new JSONObject().put("stop_id", c.getString(0)).put("stop_name", c.getString(1)));
        c.close();
        return new JSONObject().put("route_id", id).put("route_name", name).put("route_long_name", longName).put("headsign", headsign).put("stops", stops).put("source", "GTFS static schedule").put("pattern_note", "Stops follow one representative scheduled trip pattern; order can vary on other trips.");
    }

    private JSONObject activity(SQLiteDatabase db, String routeId, Map<String,String> query) throws Exception {
        String target = query.get("target_date");
        int hour = clamp(number(query.get("hour"), -1), 0, 23);
        if (target == null || hour < 0) throw new ApiError(400, "INVALID_ROUTE_TIME", "The historical date or hour is invalid.");
        Cursor r = db.rawQuery("SELECT route_id,coalesce(nullif(route_short_name,''),nullif(route_long_name,''),route_id),coalesce(route_short_name,'') FROM routes WHERE route_id=?", new String[]{routeId});
        if (!r.moveToFirst()) { r.close(); throw new ApiError(404, "UNKNOWN_ROUTE", "That route is not in the bundled schedule."); }
        String label = r.getString(1), shortName = r.getString(2); r.close();
        boolean candidate = false; JSONArray observations = new JSONArray(); double total = 0, transactions = 0;
        if (!shortName.isEmpty()) {
            Cursor exists = db.rawQuery("SELECT 1 FROM etm_route_activity WHERE route_label=? LIMIT 1", new String[]{shortName}); candidate = exists.moveToFirst(); exists.close();
            if (candidate) {
                Cursor rows = db.rawQuery("SELECT service_date,passenger_volume,transaction_count FROM etm_route_activity WHERE route_label=? AND transaction_hour=? AND day_of_week=? AND service_date<? ORDER BY service_date DESC", new String[]{shortName,String.valueOf(hour),String.valueOf(weekday(target)),target});
                while (rows.moveToNext()) { observations.put(new JSONObject().put("date",rows.getString(0)).put("passenger_volume",rows.getLong(1)).put("transaction_count",rows.getLong(2))); total+=rows.getLong(1); transactions+=rows.getLong(2); }
                rows.close();
                if (observations.length()==0) {
                    rows=db.rawQuery("SELECT service_date,passenger_volume,transaction_count FROM etm_route_activity WHERE route_label=? AND transaction_hour=? AND service_date<? ORDER BY service_date DESC",new String[]{shortName,String.valueOf(hour),target});
                    while(rows.moveToNext()){observations.put(new JSONObject().put("date",rows.getString(0)).put("passenger_volume",rows.getLong(1)).put("transaction_count",rows.getLong(2)));total+=rows.getLong(1);transactions+=rows.getLong(2);}
                    rows.close();
                }
            }
        }
        int count=observations.length();
        String status=!candidate?"unavailable":count>=3?"available":"insufficient_history";
        String basis=count>0&&observations.length()>0?"same route label candidate, weekday, and transaction hour":"same route label candidate, weekday, and transaction hour";
        Cursor meta=db.rawQuery("SELECT value FROM metadata WHERE key='historical_limitations'",null);String limits=meta.moveToFirst()?meta.getString(0):"[]";meta.close();
        JSONArray limitations;try{limitations=new JSONArray(limits);}catch(Exception e){limitations=new JSONArray();}
        JSONObject out=new JSONObject().put("route_id",routeId).put("route_label",label).put("target_date",target).put("transaction_hour",hour).put("weekday",weekdayName(target)).put("status",status).put("metric","historical_ticket_activity").put("matching_basis",basis).put("comparable_day_count",count).put("average_passenger_volume",count==0?JSONObject.NULL:Math.round(total/count*100.0)/100.0).put("average_transaction_count",count==0?JSONObject.NULL:Math.round(transactions/count*100.0)/100.0).put("observations",observations).put("source","October 2026 ETM ticket records").put("timestamp_basis","ticket transaction time; not confirmed boarding time").put("route_match_status",candidate?"exact_label_candidate_unverified":"no_exact_label_candidate").put("limitations",limitations);
        return out;
    }

    private JSONObject journeySearch(SQLiteDatabase db, JSONObject request) throws Exception {
        String origin=request.getString("origin_stop_id"), destination=request.getString("destination_stop_id");
        int maxTransfers=clamp(request.optInt("max_transfers",1),0,3); String routeFilter=request.optString("route_id","");
        Date instant=parseInstant(request.getString("departure_datetime"));
        Calendar local=Calendar.getInstance(TimeZone.getTimeZone("Asia/Kolkata"),Locale.US);local.setTime(instant);
        String serviceDate=String.format(Locale.US,"%04d-%02d-%02d",local.get(Calendar.YEAR),local.get(Calendar.MONTH)+1,local.get(Calendar.DAY_OF_MONTH));
        int requested=local.get(Calendar.HOUR_OF_DAY)*3600+local.get(Calendar.MINUTE)*60+local.get(Calendar.SECOND);
        String start=getMeta(db,"schedule_start"), end=getMeta(db,"schedule_end");
        if(serviceDate.compareTo(start)<0||serviceDate.compareTo(end)>0)throw new ApiError(503,"GTFS_SERVICE_DATE_OUT_OF_RANGE","The bundled schedule does not cover this service date.");
        Set<String> active=new HashSet<>(); String weekdayColumn=weekdayColumn(serviceDate);
        Cursor services=db.rawQuery("SELECT service_id FROM calendar WHERE start_date<=? AND end_date>=? AND "+weekdayColumn+"='1'",new String[]{serviceDate.replace("-",""),serviceDate.replace("-","")});
        while(services.moveToNext())active.add(services.getString(0));services.close();
        if(active.isEmpty())throw new ApiError(503,"NO_SERVICE_DATE","The static calendar has no active trips for this date.");
        List<PathState> frontier=new ArrayList<>();frontier.add(new PathState(origin,requested,new ArrayList<PathLeg>()));
        Map<String,List<PathLeg>> found=new LinkedHashMap<>();
        for(int depth=0;depth<=maxTransfers&&!frontier.isEmpty();depth++){
            Map<String,PathState> next=new HashMap<>();
            for(PathState current:frontier){
                int earliest=current.time+(current.legs.isEmpty()?0:300);
                String sql="SELECT st.trip_id,st.stop_sequence,st.departure_seconds,t.route_id,t.service_id FROM stop_times st JOIN trips t USING(trip_id) WHERE st.stop_id=? AND st.departure_seconds>=? ORDER BY st.departure_seconds LIMIT 2500";
                Cursor boards=db.rawQuery(sql,new String[]{current.stop,String.valueOf(earliest)});
                while(boards.moveToNext()){
                    String tripId=boards.getString(0),routeId=boards.getString(3),service=boards.getString(4);int sequence=boards.getInt(1),dep=boards.getInt(2);
                    if(!active.contains(service)||(!routeFilter.isEmpty()&&!routeFilter.equals(routeId)))continue;
                    boolean reused=false;for(PathLeg existing:current.legs)if(existing.tripId.equals(tripId)){reused=true;break;}if(reused)continue;
                    Cursor events=db.rawQuery("SELECT st.stop_sequence,st.stop_id,coalesce(s.stop_name,s.stop_id),st.arrival_seconds,st.departure_seconds FROM stop_times st JOIN stops s USING(stop_id) WHERE st.trip_id=? AND st.stop_sequence>? ORDER BY st.stop_sequence",new String[]{tripId,String.valueOf(sequence)});
                    JSONArray pathStops=new JSONArray();
                    Cursor fromCur=db.rawQuery("SELECT stop_id,coalesce(stop_name,stop_id) FROM stops WHERE stop_id=?",new String[]{current.stop});
                    String fromName=current.stop;if(fromCur.moveToFirst())fromName=fromCur.getString(1);fromCur.close();pathStops.put(current.stop);
                    while(events.moveToNext()){
                        if(events.isNull(3))continue;int arr=events.getInt(3);String to=events.getString(1),toName=events.getString(2);pathStops.put(to);
                        if(arr<=dep)continue;
                        PathLeg leg=new PathLeg(tripId,routeId,current.stop,fromName,to,toName,dep,arr,new JSONArray(pathStops.toString()));
                        List<PathLeg> path=new ArrayList<>(current.legs);path.add(leg);
                        PathState previous=next.get(to);boolean improves=previous==null||arr<previous.time;
                        if(improves)next.put(to,new PathState(to,arr,path));
                        if(to.equals(destination)){
                            StringBuilder key=new StringBuilder();for(PathLeg item:path)key.append(item.tripId).append('|');found.put(key.toString(),path);
                        }
                    }
                    events.close();
                }
                boards.close();
            }
            frontier=new ArrayList<>(next.values());
        }
        List<List<PathLeg>> options=new ArrayList<>(found.values());
        Collections.sort(options,new Comparator<List<PathLeg>>(){public int compare(List<PathLeg>a,List<PathLeg>b){int aa=a.get(a.size()-1).arrival,bb=b.get(b.size()-1).arrival;if(aa!=bb)return aa-bb;if(a.size()!=b.size())return a.size()-b.size();return a.get(0).departure-b.get(0).departure;}});
        JSONArray optionArray=new JSONArray();int total=Math.min(100,options.size());
        String preference=request.optString("preference","balanced");
        int maxElapsed=1;for(int i=0;i<total;i++){List<PathLeg> p=options.get(i);maxElapsed=Math.max(maxElapsed,p.get(p.size()-1).arrival-p.get(0).departure);}
        for(int i=0;i<total;i++)optionArray.put(optionJson(db,options.get(i),requested,serviceDate,preference,maxElapsed,maxTransfers));
        String message=total==0?(routeFilter.isEmpty()?"No scheduled journey was found for this service date and departure time.":"No scheduled journey using this route was found."):null;
        return new JSONObject().put("options",optionArray).put("origin_stop_id",origin).put("destination_stop_id",destination).put("preference",preference).put("data_source","GTFS static schedule").put("data_status","scheduled").put("generated_at",new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'",Locale.US).format(new Date())).put("crowd_data_available",false).put("walking_connections_available",false).put("ranking_note","Schedule-based journeys are searched on this device. Historical route-hour ticket activity is separate from live crowding.").put("message",message==null?JSONObject.NULL:message);
    }

    private JSONObject optionJson(SQLiteDatabase db,List<PathLeg> legs,int requested,String date,String preference,int scale,int maxTransfers)throws Exception{
        JSONArray legArray=new JSONArray(),transferStops=new JSONArray();List<JSONObject> fareEstimates=new ArrayList<>();int wait=Math.max(0,legs.get(0).departure-requested);
        for(int i=0;i<legs.size();i++){
            PathLeg leg=legs.get(i);if(i>0){wait+=Math.max(0,leg.departure-legs.get(i-1).arrival);transferStops.put(legs.get(i-1).toName);}
            String routeName=routeLabel(db,leg.routeId);
            JSONObject legFare = fareEstimate(db, leg);
            legArray.put(new JSONObject().put("trip_id",leg.tripId).put("route_id",leg.routeId).put("route_name",routeName)
                .put("from_stop",new JSONObject().put("stop_id",leg.from).put("stop_name",leg.fromName))
                .put("to_stop",new JSONObject().put("stop_id",leg.to).put("stop_name",leg.toName))
                .put("departure_datetime",scheduledDateTime(date,leg.departure)).put("arrival_datetime",scheduledDateTime(date,leg.arrival))
                .put("stop_sequence",leg.stopSequence).put("eta_source","GTFS static schedule")
                .put("fare_estimate",legFare));
            fareEstimates.add(legFare);
        }
        boolean allFares=true;int ordinaryTotal=0,acTotal=0,estimatedLegs=0;double distanceTotal=0;
        for(JSONObject fare:fareEstimates){if(!"estimated".equals(fare.optString("status"))){allFares=false;continue;}estimatedLegs++;ordinaryTotal+=fare.optInt("ordinary_adult_fare_inr");acTotal+=fare.optInt("ac_adult_fare_inr");distanceTotal+=fare.optDouble("estimated_distance_km");}
        JSONObject journeyFare=new JSONObject().put("status",estimatedLegs==0?"unavailable":allFares?"estimated":"partial").put("currency","INR").put("estimated_leg_count",estimatedLegs).put("total_leg_count",legs.size()).put("ordinary_adult_total_inr",allFares&&estimatedLegs>0?ordinaryTotal:JSONObject.NULL).put("ac_adult_total_inr",allFares&&estimatedLegs>0?acTotal:JSONObject.NULL).put("estimated_distance_km",allFares&&estimatedLegs>0?Math.round(distanceTotal*10.0)/10.0:JSONObject.NULL).put("note","Estimated per bus leg from GTFS route shape distance and Delhi adult fare bands; actual service, fare stages and concessions may differ.");
        PathLeg first=legs.get(0),last=legs.get(legs.size()-1);int elapsed=last.arrival-first.departure;double timeComponent=(elapsed+Math.max(0,first.departure-requested))/(double)scale;double transferComponent=(legs.size()-1)/(double)Math.max(maxTransfers,1);double score="fastest".equals(preference)?timeComponent:.5*timeComponent+.5*transferComponent;
        return new JSONObject().put("legs",legArray).put("departure_datetime",scheduledDateTime(date,first.departure)).put("arrival_datetime",scheduledDateTime(date,last.arrival)).put("duration_seconds",elapsed).put("waiting_seconds",wait).put("transfers",legs.size()-1).put("transfer_stops",transferStops)
            .put("fare_estimate",journeyFare)
            .put("eta_source","GTFS static schedule").put("crowd_status","unavailable").put("score",score).put("score_components",new JSONObject().put("time",timeComponent).put("crowd",JSONObject.NULL).put("transfers",transferComponent));
    }

    private JSONObject fareEstimate(SQLiteDatabase db,PathLeg leg)throws Exception{
        Cursor shape=db.rawQuery("SELECT shape_id FROM trips WHERE trip_id=?",new String[]{leg.tripId});
        String shapeId=shape.moveToFirst()?shape.getString(0):null;shape.close();
        Cursor stopCoords=db.rawQuery("SELECT stop_id,stop_lat,stop_lon FROM stops WHERE stop_id IN (?,?)",new String[]{leg.from,leg.to});
        double fromLat=0,fromLon=0,toLat=0,toLon=0;boolean hasFrom=false,hasTo=false;
        while(stopCoords.moveToNext()){if(stopCoords.isNull(1)||stopCoords.isNull(2))continue;if(leg.from.equals(stopCoords.getString(0))){fromLat=stopCoords.getDouble(1);fromLon=stopCoords.getDouble(2);hasFrom=true;}if(leg.to.equals(stopCoords.getString(0))){toLat=stopCoords.getDouble(1);toLon=stopCoords.getDouble(2);hasTo=true;}}stopCoords.close();
        if(shapeId==null||!hasFrom||!hasTo)return unavailableFare("A route shape or stop coordinates are not available for this bus leg.");
        Cursor points=db.rawQuery("SELECT shape_pt_lat,shape_pt_lon FROM shapes WHERE shape_id=? ORDER BY shape_pt_sequence",new String[]{shapeId});
        List<double[]> coords=new ArrayList<>();while(points.moveToNext())if(!points.isNull(0)&&!points.isNull(1))coords.add(new double[]{points.getDouble(0),points.getDouble(1)});points.close();
        if(coords.size()<2)return unavailableFare("The scheduled route shape is incomplete.");
        int fromIndex=-1,toIndex=-1;double fromSnap=Double.MAX_VALUE,toSnap=Double.MAX_VALUE,bestSnapSum=Double.MAX_VALUE;
        for(int i=0;i<coords.size();i++){double d1=distanceMeters(coords.get(i)[0],coords.get(i)[1],fromLat,fromLon);if(d1>1000)continue;for(int j=i+1;j<coords.size();j++){double d2=distanceMeters(coords.get(j)[0],coords.get(j)[1],toLat,toLon);if(d2<=1000&&d1+d2<bestSnapSum){bestSnapSum=d1+d2;fromIndex=i;toIndex=j;fromSnap=d1;toSnap=d2;}}}
        if(fromIndex<0||toIndex<=fromIndex)return unavailableFare("The stop pair could not be matched to the scheduled route shape.");
        double meters=fromSnap+toSnap;for(int i=fromIndex;i<toIndex;i++)meters+=distanceMeters(coords.get(i)[0],coords.get(i)[1],coords.get(i+1)[0],coords.get(i+1)[1]);
        double km=meters/1000.0;if(km<=0)return unavailableFare("The scheduled route distance is not valid.");
        int ordinary=km<=4?5:km<=10?10:15;int ac=km<=4?10:km<=8?15:km<=12?20:25;
        return new JSONObject().put("status","estimated").put("currency","INR").put("estimated_distance_km",Math.round(km*100.0)/100.0).put("fare_stage_intervals",JSONObject.NULL).put("ordinary_adult_fare_inr",ordinary).put("ac_adult_fare_inr",ac).put("confidence","medium").put("basis","GTFS scheduled route shape distance and Delhi Tourism published fare bands").put("note","Estimated adult single-ride fare. Actual ticket depends on operator, fare stages, service type and concessions.");
    }

    private JSONObject unavailableFare(String note)throws Exception{return new JSONObject().put("status","unavailable").put("currency","INR").put("estimated_distance_km",JSONObject.NULL).put("fare_stage_intervals",JSONObject.NULL).put("ordinary_adult_fare_inr",JSONObject.NULL).put("ac_adult_fare_inr",JSONObject.NULL).put("confidence","unavailable").put("basis","GTFS scheduled route shape distance").put("note",note);}
    private static double distanceMeters(double lat1,double lon1,double lat2,double lon2){double a=Math.toRadians(lat1),b=Math.toRadians(lat2),dLat=Math.toRadians(lat2-lat1),dLon=Math.toRadians(lon2-lon1);double h=Math.sin(dLat/2)*Math.sin(dLat/2)+Math.cos(a)*Math.cos(b)*Math.sin(dLon/2)*Math.sin(dLon/2);return 12742000*Math.asin(Math.min(1,Math.sqrt(h)));}

    private JSONObject saveReport(SQLiteDatabase db,JSONObject body,String clientToken)throws Exception{
        String stopId=body.optString("stop_id"),category=body.optString("category"),routeId=body.isNull("route_id")?null:body.optString("route_id");
        if(stopId.isEmpty())throw new ApiError(422,"STOP_REQUIRED","Choose a stop before sending the crowd report.");
        if(!"low".equals(category)&&!"moderate".equals(category)&&!"high".equals(category)&&!"very_high".equals(category))throw new ApiError(422,"CATEGORY_REQUIRED","Choose a crowd level before sending the report.");
        Cursor stop=db.rawQuery("SELECT coalesce(stop_name,stop_id) FROM stops WHERE stop_id=?",new String[]{stopId});if(!stop.moveToFirst()){stop.close();throw new ApiError(404,"UNKNOWN_STOP","That stop is not in the bundled Delhi dataset.");}String stopName=stop.getString(0);stop.close();
        if(routeId!=null&&!routeId.isEmpty()){Cursor route=db.rawQuery("SELECT 1 FROM routes WHERE route_id=?",new String[]{routeId});boolean exists=route.moveToFirst();route.close();if(!exists)throw new ApiError(422,"UNKNOWN_ROUTE","Select a route from the bundled route list.");}else routeId=null;
        long now=System.currentTimeMillis(),expiry=now+20*60*1000L;String observed=body.optString("observed_at");if(observed.isEmpty())observed=isoTime(now);
        JSONArray stored=readReports(now),next=new JSONArray();String reportId=UUID.randomUUID().toString();boolean replaced=false;
        for(int i=0;i<stored.length();i++){JSONObject item=stored.optJSONObject(i);if(item==null)continue;if(stopId.equals(item.optString("stop_id"))&&clientToken.equals(item.optString("client_token"))){if(!replaced){JSONObject replacement=reportObject(reportId,stopId,stopName,routeId,category,body.optString("feedback_code"),observed,now,expiry,clientToken);next.put(replacement);replaced=true;}continue;}next.put(item);}
        if(!replaced)next.put(reportObject(reportId,stopId,stopName,routeId,category,body.optString("feedback_code"),observed,now,expiry,clientToken));
        if(next.length()>200){JSONArray limited=new JSONArray();for(int i=next.length()-200;i<next.length();i++)limited.put(next.getJSONObject(i));next=limited;}
        reportStore.edit().putString("reports",next.toString()).apply();
        JSONObject response=reportObject(reportId,stopId,stopName,routeId,category,body.optString("feedback_code"),observed,now,expiry,clientToken);response.remove("expires_ms");response.remove("client_token");response.put("status","COMMUNITY_REPORTED").put("observation_type","subjective_category_not_headcount").put("stop_identity_status","gtfs_stop_id").put("local_only",true);return response;
    }

    private JSONObject reportObject(String id,String stopId,String stopName,String routeId,String category,String feedback,String observed,long created,long expires,String token)throws Exception{
        JSONObject row=new JSONObject().put("report_id",id).put("stop_id",stopId).put("stop_name",stopName).put("route_id",routeId==null?JSONObject.NULL:routeId).put("category",category).put("feedback_code",feedback==null||feedback.isEmpty()||"null".equals(feedback)?JSONObject.NULL:feedback).put("observed_at",observed).put("created_at",isoTime(created)).put("expires_at",isoTime(expires)).put("expires_ms",expires).put("client_token",token);return row;
    }
    private JSONArray readReports(long now)throws Exception{JSONArray old;try{old=new JSONArray(reportStore.getString("reports","[]"));}catch(Exception e){old=new JSONArray();}JSONArray active=new JSONArray();for(int i=0;i<old.length();i++){JSONObject item=old.optJSONObject(i);if(item!=null&&item.optLong("expires_ms",0)>now)active.put(item);}if(active.length()!=old.length())reportStore.edit().putString("reports",active.toString()).apply();return active;}
    private JSONObject localReports(SQLiteDatabase db,String stopId)throws Exception{Cursor c=db.rawQuery("SELECT coalesce(stop_name,stop_id) FROM stops WHERE stop_id=?",new String[]{stopId});if(!c.moveToFirst()){c.close();throw new ApiError(404,"UNKNOWN_STOP","That stop is not in the bundled Delhi dataset.");}String name=c.getString(0);c.close();JSONArray all=readReports(System.currentTimeMillis()),items=new JSONArray();for(int i=0;i<all.length();i++){JSONObject row=new JSONObject(all.getJSONObject(i).toString());row.remove("expires_ms");row.remove("client_token");if(stopId.equals(row.optString("stop_id")))items.put(row);}return new JSONObject().put("stop_id",stopId).put("status",items.length()>0?"COMMUNITY_REPORTED":"UNAVAILABLE").put("source","community_reports").put("stop_name",name).put("report_count",items.length()).put("reports",items).put("generated_at",isoTime(System.currentTimeMillis())).put("limitations",new JSONArray().put("Reports are voluntary rider observations, not measured passenger counts.").put("Reports on this device are not synchronized with other devices."));}
    private JSONObject localCrowd(SQLiteDatabase db,String stopId)throws Exception{JSONObject reports=localReports(db,stopId);JSONArray items=reports.getJSONArray("reports");Map<String,Integer> counts=new HashMap<>();for(int i=0;i<items.length();i++){String category=items.getJSONObject(i).getString("category");counts.put(category,counts.containsKey(category)?counts.get(category)+1:1);}String best=null;int max=0;for(String category:counts.keySet())if(counts.get(category)>max){best=category;max=counts.get(category);}return new JSONObject().put("stop_id",stopId).put("stop_name",reports.optString("stop_name")).put("status",items.length()>0?"COMMUNITY_REPORTED":"UNAVAILABLE").put("observation_type","community_category_aggregate").put("crowd_category",best==null?JSONObject.NULL:best).put("report_count",items.length()).put("agreement_fraction",items.length()>0?(double)max/items.length():JSONObject.NULL).put("evidence_quality",items.length()>1?"limited_community_sample":"insufficient_reports").put("generated_at",isoTime(System.currentTimeMillis())).put("freshness_seconds",items.length()>0?0:JSONObject.NULL).put("limitations",reports.getJSONArray("limitations"));}
    private static String isoTime(long millis){SimpleDateFormat f=new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",Locale.US);f.setTimeZone(TimeZone.getTimeZone("UTC"));return f.format(new Date(millis));}

    private JSONObject overview(SQLiteDatabase db)throws Exception{
        Cursor m=db.rawQuery("SELECT value FROM metadata WHERE key='historical_rows'",null);long rows=m.moveToFirst()?Long.parseLong(m.getString(0)):0;m.close();
        Cursor s=db.rawQuery("SELECT min(service_date),max(service_date),count(distinct route_label) FROM etm_route_activity",null);s.moveToFirst();String min=s.getString(0),max=s.getString(1);int labels=s.getInt(2);s.close();
        return new JSONObject().put("data_source","October 2026 ETM ticket records (historical snapshot)").put("dataset_rows",rows).put("dataset_min_timestamp",min).put("dataset_max_timestamp",max).put("distinct_routes",labels);
    }
    private JSONObject trends(SQLiteDatabase db)throws Exception{
        JSONArray items=new JSONArray();Cursor c=db.rawQuery("SELECT service_date,sum(passenger_volume),sum(transaction_count) FROM etm_route_activity GROUP BY service_date ORDER BY service_date",null);
        while(c.moveToNext())items.put(new JSONObject().put("date",c.getString(0)).put("passenger_volume",c.getLong(1)).put("transaction_count",c.getLong(2)));c.close();return new JSONObject().put("items",items);
    }
    private JSONObject corridors(SQLiteDatabase db,int limit)throws Exception{
        JSONArray items=new JSONArray();Cursor c=db.rawQuery("SELECT route_label,sum(passenger_volume),sum(transaction_count) FROM etm_route_activity GROUP BY route_label ORDER BY sum(passenger_volume) DESC LIMIT ?",new String[]{String.valueOf(clamp(limit,1,50))});
        while(c.moveToNext())items.put(new JSONObject().put("route_label",c.getString(0)).put("passenger_volume",c.getLong(1)).put("transaction_count",c.getLong(2)));c.close();return new JSONObject().put("items",items);
    }

    private String routeLabel(SQLiteDatabase db,String id){Cursor c=db.rawQuery("SELECT coalesce(nullif(route_short_name,''),nullif(route_long_name,''),route_id) FROM routes WHERE route_id=?",new String[]{id});String value=c.moveToFirst()?c.getString(0):id;c.close();return value;}
    private static Map<String,String> parseQuery(String q)throws Exception{Map<String,String> out=new HashMap<>();if(q.isEmpty())return out;for(String pair:q.split("&")){String[] p=pair.split("=",2);out.put(decode(p[0]),p.length>1?decode(p[1]):"");}return out;}
    private static String decode(String value){try{return URLDecoder.decode(value,"UTF-8");}catch(Exception e){return value;}}
    private static int number(String value,int fallback){try{return Integer.parseInt(value);}catch(Exception e){return fallback;}}
    private static int clamp(int value,int low,int high){return Math.max(low,Math.min(high,value));}
    private static String getMeta(SQLiteDatabase db,String key){Cursor c=db.rawQuery("SELECT value FROM metadata WHERE key=?",new String[]{key});String value=c.moveToFirst()?c.getString(0):"";c.close();return value;}
    private static Date parseInstant(String value)throws Exception{SimpleDateFormat f=new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",Locale.US);f.setTimeZone(TimeZone.getTimeZone("UTC"));try{return f.parse(value);}catch(Exception e){SimpleDateFormat f2=new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'",Locale.US);f2.setTimeZone(TimeZone.getTimeZone("UTC"));return f2.parse(value);}}
    private static String scheduledDateTime(String date,int seconds){try{Calendar c=Calendar.getInstance(TimeZone.getTimeZone("Asia/Kolkata"),Locale.US);String[] p=date.split("-");c.set(Integer.parseInt(p[0]),Integer.parseInt(p[1])-1,Integer.parseInt(p[2]),0,0,0);c.set(Calendar.MILLISECOND,0);c.add(Calendar.SECOND,seconds);return new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX",Locale.US).format(c.getTime());}catch(Exception e){return date+"T00:00:00+05:30";}}
    private static int weekday(String date){String[] p=date.split("-");Calendar c=Calendar.getInstance(Locale.US);c.set(Integer.parseInt(p[0]),Integer.parseInt(p[1])-1,Integer.parseInt(p[2]));return (c.get(Calendar.DAY_OF_WEEK)+5)%7;}
    private static String weekdayName(String date){return new String[]{"Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"}[weekday(date)];}
    private static String weekdayColumn(String date){return new String[]{"monday","tuesday","wednesday","thursday","friday","saturday","sunday"}[weekday(date)];}

    private static final class PathState{final String stop;final int time;final List<PathLeg> legs;PathState(String s,int t,List<PathLeg> l){stop=s;time=t;legs=l;}}
    private static final class PathLeg{final String tripId,routeId,from,fromName,to,toName;final int departure,arrival;final JSONArray stopSequence;PathLeg(String ti,String ri,String f,String fn,String t,String tn,int d,int a,JSONArray seq){tripId=ti;routeId=ri;from=f;fromName=fn;to=t;toName=tn;departure=d;arrival=a;stopSequence=seq;}}
    private static final class ApiError extends Exception{final int status;final String code;ApiError(int s,String c,String m){super(m);status=s;code=c;}}
}
