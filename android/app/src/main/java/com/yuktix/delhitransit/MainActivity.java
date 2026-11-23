package com.yuktix.delhitransit;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.TextView;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.zip.GZIPInputStream;

public final class MainActivity extends Activity {
    private static final String APP_URL = "http://127.0.0.1:18321/";
    private WebView webView;
    private OfflineWebServer server;
    private TextView status;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(255, 248, 243));
        status = new TextView(this);
        status.setText("Preparing your offline Delhi schedule…\n\nThis happens only the first time.");
        status.setTextColor(Color.rgb(65, 43, 38));
        status.setTextSize(18);
        status.setGravity(17);
        root.addView(status, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);
        new Thread(() -> {
            try {
                File db = new File(getFilesDir(), "offline.db");
                if (!db.exists() || db.length() == 0 || databaseNeedsShapeUpgrade(db)) extractDatabase(db);
                OfflineWebServer localServer = new OfflineWebServer(this);
                localServer.start();
                runOnUiThread(() -> openApp(root, localServer, db));
            } catch (Exception e) {
                Log.e("YuktixOffline", "Failed to prepare offline app", e);
                runOnUiThread(() -> status.setText("Offline data could not be prepared. Please reinstall Yuktix and try again."));
            }
        }, "yuktix-offline-setup").start();
    }

    private boolean databaseNeedsShapeUpgrade(File database) {
        android.database.sqlite.SQLiteDatabase check = null;
        try {
            check = android.database.sqlite.SQLiteDatabase.openDatabase(database.getAbsolutePath(), null, android.database.sqlite.SQLiteDatabase.OPEN_READONLY);
            android.database.Cursor cursor = check.rawQuery("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='shapes'", null);
            boolean missing = !cursor.moveToFirst() || cursor.getInt(0) == 0;
            cursor.close();
            return missing;
        } catch (Exception ignored) { return true; }
        finally { if (check != null) check.close(); }
    }

    private void extractDatabase(File target) throws Exception {
        File temp = new File(getFilesDir(), "offline.db.tmp");
        try (InputStream raw = getAssets().open("offline.db.gz");
             GZIPInputStream gzip = new GZIPInputStream(raw);
             FileOutputStream out = new FileOutputStream(temp)) {
            byte[] buffer = new byte[65536]; int n; long expanded = 0, nextUpdate = 32L * 1024 * 1024;
            while ((n = gzip.read(buffer)) != -1) {
                out.write(buffer, 0, n); expanded += n;
                if (expanded >= nextUpdate) {
                    final long megabytes = expanded / (1024 * 1024);
                    runOnUiThread(() -> status.setText("Preparing your offline Delhi schedule…\n\n" + megabytes + " MB unpacked"));
                    nextUpdate += 32L * 1024 * 1024;
                }
            }
            out.getFD().sync();
        }
        if (!temp.renameTo(target)) {
            if (target.exists() && !target.delete()) throw new Exception("Could not replace the older offline data");
            if (!temp.renameTo(target)) throw new Exception("Could not save offline data");
        }
    }

    private void openApp(FrameLayout root, OfflineWebServer localServer, File db) {
        server = localServer;
        webView = new WebView(this);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        webView.addJavascriptInterface(new OfflineApi(this, db), "YuktixOffline");
        webView.addJavascriptInterface(new Object() { @JavascriptInterface public boolean enabled() { return true; } }, "YuktixShell");
        webView.setWebViewClient(new WebViewClient() {
            private boolean isLocal(String url) { return url != null && (url.startsWith("http://127.0.0.1:18321/") || url.startsWith("http://localhost:18321/")); }
            @Override public boolean shouldOverrideUrlLoading(WebView view, String url) { return !isLocal(url); }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) { return !isLocal(request.getUrl().toString()); }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                if (isLocal(request.getUrl().toString())) return null;
                return new WebResourceResponse("text/plain", "UTF-8", 403, "Offline", null, new java.io.ByteArrayInputStream(new byte[0]));
            }
        });
        root.removeView(status);
        root.addView(webView, new FrameLayout.LayoutParams(-1, -1));
        webView.loadUrl(APP_URL);
    }

    @Override public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack(); else super.onBackPressed();
    }

    @Override protected void onDestroy() {
        if (server != null) server.stop();
        if (webView != null) { webView.destroy(); webView = null; }
        super.onDestroy();
    }
}
