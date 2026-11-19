package dz.krouchi.app;

import android.app.Activity;
import android.os.Bundle;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Krouchi_DZ — رفيق الهاتف لبرنامج Krouchi_DZ المكتبي (شيفرة أصلية).
 *
 * نشاط واحد يستضيف واجهة HTML/JS من أصول التطبيق عبر نطاق وهمي
 * محلي (https://krouchi.local/)، ويقدّم للواجهة جسر HTTP أصيلاً
 * (HttpURLConnection) حتى تعمل طلبات اكتشاف النماذج والمحادثة
 * بمفتاح المستخدم دون قيود CORS الخاصة بالويب فيو.
 *
 * النسخة 2.0: إدخال API + اكتشاف نماذج + محادثة محلية، ووضع
 * مرافق للحاسوب: الاتصال بخادم Krouchi_DZ المكتبي على الشبكة
 * المحلية (http://<pc>:8765 + ترويسة X-Krouchi-Token) للمحادثة
 * عبر بوتات الحاسوب والموافقة على طلبات تنفيذه أو رفضها.
 * لا أدوات ملفات ولا أوامر على الهاتف نفسه. المفاتيح والبيانات
 * في تخزين التطبيق الخاص (DOM Storage للويب فيو).
 */
public class MainActivity extends Activity {

    private static final String ASSET_HOST = "https://krouchi.local/";
    private static final String HOME_URL = ASSET_HOST + "index.html";

    private WebView webView;
    private final ExecutorService httpPool = Executors.newCachedThreadPool();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view,
                                                              WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (url.startsWith(ASSET_HOST)) {
                    String name = url.substring(ASSET_HOST.length());
                    int q = name.indexOf('?');
                    if (q >= 0) name = name.substring(0, q);
                    if (name.equals("index.html") || name.equals("app.js")) {
                        try {
                            InputStream is = getAssets().open(name);
                            String mime = name.endsWith(".js")
                                    ? "application/javascript" : "text/html";
                            return new WebResourceResponse(mime, "UTF-8", is);
                        } catch (IOException e) {
                            return null;
                        }
                    }
                }
                return null;
            }
        });

        webView.addJavascriptInterface(new Bridge(), "KrouchiBridge");
        webView.loadUrl(HOME_URL);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        httpPool.shutdownNow();
        super.onDestroy();
    }

    /**
     * جسر JavaScript: طلب HTTP أصيل من الواجهة.
     *
     * http(reqId, method, url, headersJson, body[, readTimeoutMs])
     *   headersJson: كائن JSON {name: value} أو "" لغياب الترويسات.
     *   body: نص الطلب أو "" لطلب بلا جسم.
     *   readTimeoutMs (اختياري): مهلة قراءة بالميلي ثانية (افتراضي 90s،
     *   تُقصّ بين 15s و300s) — لمحادثة الحاسوب المنتظِرة موافقة.
     * النتيجة تصل إلى window.__krouchiHttpDone(reqId, status, bodyB64, error)
     * حيث status=0 عند فشل شبكي (error يصف السبب)، و bodyB64 هو جسم
     * الردّ مشفّراً بـ Base64 (قد يكون "" عند الخطأ الشبكي).
     */
    public class Bridge {

        @JavascriptInterface
        public void toast(final String msg) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    Toast.makeText(MainActivity.this, msg, Toast.LENGTH_LONG).show();
                }
            });
        }

        @JavascriptInterface
        public void http(final String reqId, final String method, final String url,
                         final String headersJson, final String body) {
            doHttp(reqId, method, url, headersJson, body, 90000);
        }

        /**
         * صيغة بمهلة قراءة ممتدة: محادثة الحاسوب قد تنتظر موافقة
         * على جانب الحاسوب حتى ~120 ثانية، فنسمح حتى 300 ثانية.
         */
        @JavascriptInterface
        public void http(final String reqId, final String method, final String url,
                         final String headersJson, final String body,
                         final int readTimeoutMs) {
            int rt = readTimeoutMs;
            if (rt < 15000) rt = 15000;
            if (rt > 300000) rt = 300000;
            doHttp(reqId, method, url, headersJson, body, rt);
        }

        private void doHttp(final String reqId, final String method, final String url,
                            final String headersJson, final String body,
                            final int readTimeoutMs) {
            httpPool.execute(new Runnable() {
                @Override
                public void run() {
                    int status = 0;
                    String responseText = "";
                    String error = "";
                    HttpURLConnection conn = null;
                    try {
                        conn = (HttpURLConnection) new URL(url).openConnection();
                        conn.setRequestMethod(method == null ? "GET" : method);
                        conn.setConnectTimeout(20000);
                        conn.setReadTimeout(readTimeoutMs);
                        if (headersJson != null && !headersJson.trim().isEmpty()) {
                            JSONObject headers = new JSONObject(headersJson);
                            Iterator<String> keys = headers.keys();
                            while (keys.hasNext()) {
                                String k = keys.next();
                                conn.setRequestProperty(k, headers.optString(k));
                            }
                        }
                        if (body != null && !body.isEmpty()) {
                            byte[] payload = body.getBytes(StandardCharsets.UTF_8);
                            conn.setDoOutput(true);
                            conn.setRequestProperty("Content-Length",
                                    String.valueOf(payload.length));
                            OutputStream os = conn.getOutputStream();
                            os.write(payload);
                            os.flush();
                            os.close();
                        }
                        status = conn.getResponseCode();
                        InputStream is = status >= 400
                                ? conn.getErrorStream() : conn.getInputStream();
                        if (is != null) {
                            responseText = readAll(is);
                        }
                    } catch (Exception e) {
                        status = 0;
                        error = e.getClass().getSimpleName()
                                + (e.getMessage() != null ? ": " + e.getMessage() : "");
                    } finally {
                        if (conn != null) conn.disconnect();
                    }
                    deliver(reqId, status, responseText, error);
                }
            });
        }

        private String readAll(InputStream is) throws IOException {
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(is, StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            char[] buf = new char[4096];
            int n;
            while ((n = reader.read(buf)) > 0) {
                sb.append(buf, 0, n);
            }
            reader.close();
            return sb.toString();
        }

        private void deliver(final String reqId, final int status,
                             final String responseText, final String error) {
            final String bodyB64 = Base64.encodeToString(
                    responseText.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
            final String js = "window.__krouchiHttpDone && window.__krouchiHttpDone("
                    + JSONObject.quote(reqId) + ", " + status + ", "
                    + JSONObject.quote(bodyB64) + ", "
                    + JSONObject.quote(error) + ");";
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    if (webView != null) webView.evaluateJavascript(js, null);
                }
            });
        }
    }
}
