import { useState } from "react";
import CandlestickChart from "../components/CandlestickChart";
import RSIChart from "../components/RSIChart";

type StockData = {
  time: string | number;
  open: number;
  high: number;
  low: number;
  close: number;
  RSI?: number;
  [key: string]: string | number | null | undefined;
};

type ApiResponse = {
  data: StockData[];
};

export default function Home() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stockData, setStockData] = useState<StockData[] | null>(null);

  const fetchMockPrice = async () => {
    setLoading(true);
    setError(null);
    setStockData(null);

    try {
      console.log("Fetching data from http://localhost:8000/stock/mock-price");
      const res = await fetch("http://localhost:8000/stock/mock-price");

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `Request failed with status ${res.status}` }));
        console.error("API Error:", err);
        throw new Error(err?.detail ?? `Request failed with status ${res.status}`);
      }

      const json: ApiResponse = await res.json();
      console.log("Received data:", json);
      console.log("Data array:", json.data);
      
      if (!json.data || !Array.isArray(json.data)) {
        throw new Error("Invalid data format: expected array");
      }

      setStockData(json.data);
      
      if (json.data.length === 0) {
        console.warn("No data in response");
        setError("No data available");
      }
    } catch (err: any) {
      console.error("Fetch error:", err);
      setError(err.message ?? "Failed to fetch data. Make sure the backend is running on http://localhost:8000");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main
      style={{
        minHeight: "100vh",
        padding: "2rem",
        background: "#020617",
        color: "#e5e7eb",
        fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 1400,
          margin: "0 auto",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "1.5rem",
          }}
        >
          <div>
            <h1
              style={{
                fontSize: "2rem",
                fontWeight: 700,
                marginBottom: "0.5rem",
              }}
            >
              Stock Bot Dashboard
            </h1>
            <p
              style={{
                color: "#9ca3af",
                fontSize: "0.9rem",
              }}
            >
              Candlestick price chart and RSI indicator
            </p>
          </div>
          <button
            onClick={fetchMockPrice}
            disabled={loading}
            style={{
              padding: "0.6rem 1.25rem",
              borderRadius: "0.5rem",
              border: "none",
              background: loading ? "#4b5563" : "#22c55e",
              color: "#020617",
              fontWeight: 600,
              cursor: loading ? "default" : "pointer",
              transition: "background 0.15s ease-out",
            }}
          >
            {loading ? "Loading..." : "Refresh Data"}
          </button>
        </div>

        {error && (
          <div
            style={{
              marginBottom: "1.5rem",
              padding: "0.75rem 1rem",
              borderRadius: "0.5rem",
              background: "#7f1d1d",
              color: "#fee2e2",
              fontSize: "0.9rem",
            }}
          >
            {error}
          </div>
        )}

        {/* Charts - always render, even if no data yet */}
        {stockData && stockData.length > 0 ? (
          <>
            <CandlestickChart data={stockData} />
            <RSIChart data={stockData} />
          </>
        ) : (
          <>
            <div
              style={{
                marginBottom: "1.5rem",
                borderRadius: "0.75rem",
                border: "1px solid #1f2937",
                overflow: "hidden",
                background: "#020617",
                padding: "1rem",
              }}
            >
              <h2
                style={{
                  fontSize: "1.25rem",
                  fontWeight: 600,
                  marginBottom: "0.75rem",
                  color: "#e5e7eb",
                }}
              >
                Price Chart (Candlestick)
              </h2>
              <div 
                style={{ 
                  width: "100%", 
                  minHeight: "500px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#6b7280",
                }} 
              >
                {!loading && <p>Click "Refresh Data" to load chart data</p>}
              </div>
            </div>

            <div
              style={{
                marginBottom: "1.5rem",
                borderRadius: "0.75rem",
                border: "1px solid #1f2937",
                overflow: "hidden",
                background: "#020617",
                padding: "1rem",
              }}
            >
              <h2
                style={{
                  fontSize: "1.25rem",
                  fontWeight: 600,
                  marginBottom: "0.75rem",
                  color: "#e5e7eb",
                }}
              >
                RSI Indicator
              </h2>
              <div 
                style={{ 
                  width: "100%", 
                  minHeight: "300px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#6b7280",
                }} 
              >
                {!loading && <p>Click "Refresh Data" to load chart data</p>}
              </div>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
