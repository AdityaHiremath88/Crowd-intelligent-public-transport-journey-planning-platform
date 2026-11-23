package com.yuktix.delhitransit;

import android.content.Context;
import android.content.res.AssetManager;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URLDecoder;
import java.util.Locale;

/** Serves only packaged frontend assets over loopback; API calls use the local Java bridge. */
public final class OfflineWebServer implements Runnable {
    public static final int PORT = 18321;
    private final AssetManager assets;
    private volatile boolean running = true;
    private ServerSocket server;

    public OfflineWebServer(Context context) { assets = context.getAssets(); }

    public void start() throws IOException {
        server = new ServerSocket(PORT, 16, InetAddress.getByName("127.0.0.1"));
        Thread listener = new Thread(this, "yuktix-offline-assets");
        listener.setDaemon(true);
        listener.start();
    }

    @Override public void run() {
        try {
            while (running) {
                final Socket client = server.accept();
                Thread worker = new Thread(() -> handle(client), "yuktix-http-client");
                worker.setDaemon(true);
                worker.start();
            }
        } catch (IOException ignored) { }
    }

    public void stop() {
        running = false;
        try { if (server != null) server.close(); } catch (IOException ignored) { }
    }

    private void handle(Socket socket) {
        try (Socket client = socket) {
            client.setSoTimeout(5000);
            BufferedInputStream in = new BufferedInputStream(client.getInputStream());
            String line = readLine(in);
            if (line == null) return;
            String[] request = line.split(" ");
            while (true) { String header = readLine(in); if (header == null || header.isEmpty()) break; }
            if (request.length < 2 || !("GET".equals(request[0]) || "HEAD".equals(request[0]))) {
                writeResponse(client.getOutputStream(), 405, "text/plain; charset=utf-8", "Method not allowed".getBytes("UTF-8"));
                return;
            }
            String path = request[1].split("\\?", 2)[0];
            try { path = URLDecoder.decode(path, "UTF-8"); } catch (Exception ignored) { }
            if (path.equals("/")) path = "/index.html";
            if (path.contains("..") || path.contains("\\")) {
                writeResponse(client.getOutputStream(), 403, "text/plain; charset=utf-8", "Forbidden".getBytes("UTF-8"));
                return;
            }
            byte[] bytes;
            try (InputStream asset = assets.open("www" + path)) { bytes = readAll(asset); }
            catch (IOException e) {
                writeResponse(client.getOutputStream(), 404, "text/plain; charset=utf-8", "Not found".getBytes("UTF-8"));
                return;
            }
            writeResponse(client.getOutputStream(), 200, mime(path), bytes);
        } catch (Exception ignored) { }
    }

    private static String readLine(InputStream input) throws IOException {
        ByteArrayOutputStream line = new ByteArrayOutputStream();
        int previous = -1;
        while (line.size() < 8192) {
            int value = input.read();
            if (value < 0) return line.size() == 0 ? null : new String(line.toByteArray(), "UTF-8").trim();
            if (previous == '\r' && value == '\n') {
                byte[] bytes = line.toByteArray();
                return new String(bytes, 0, Math.max(0, bytes.length - 1), "UTF-8");
            }
            line.write(value); previous = value;
        }
        throw new IOException("HTTP header line too long");
    }

    private static byte[] readAll(InputStream input) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[16384]; int n;
        while ((n = input.read(buffer)) >= 0) out.write(buffer, 0, n);
        return out.toByteArray();
    }

    private static String mime(String path) {
        String lower = path.toLowerCase(Locale.ROOT);
        if (lower.endsWith(".html")) return "text/html; charset=utf-8";
        if (lower.endsWith(".js")) return "text/javascript; charset=utf-8";
        if (lower.endsWith(".css")) return "text/css; charset=utf-8";
        if (lower.endsWith(".svg")) return "image/svg+xml";
        if (lower.endsWith(".webmanifest")) return "application/manifest+json";
        if (lower.endsWith(".json")) return "application/json; charset=utf-8";
        if (lower.endsWith(".woff2")) return "font/woff2";
        return "application/octet-stream";
    }

    private static void writeResponse(OutputStream out, int status, String type, byte[] content) throws IOException {
        String reason = status == 200 ? "OK" : status == 403 ? "Forbidden" : status == 405 ? "Method Not Allowed" : "Not Found";
        String header = "HTTP/1.1 " + status + " " + reason + "\r\nContent-Type: " + type + "\r\nContent-Length: " + content.length + "\r\nCache-Control: no-store\r\nConnection: close\r\nX-Content-Type-Options: nosniff\r\n\r\n";
        out.write(header.getBytes("UTF-8")); out.write(content); out.flush();
    }
}
