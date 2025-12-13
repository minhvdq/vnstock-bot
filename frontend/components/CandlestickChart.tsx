import { useEffect, useRef } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, CandlestickSeries, LineSeries, Time } from "lightweight-charts";
import { parseTime, timeToNumber, getValue } from "./utils";

type StockData = {
  time: string | number;
  open: number;
  high: number;
  low: number;
  close: number;
  [key: string]: string | number | null | undefined;
};

interface CandlestickChartProps {
  data: StockData[];
  activeDivergence?: { prefixIndex: number; suffixIndex: number; type: string } | null;
}

export default function CandlestickChart({ data, activeDivergence }: CandlestickChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const divLineRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Initialize candlestick chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#020617" },
        textColor: "#e5e7eb",
      },
      width: chartContainerRef.current.clientWidth,
      height: 500,
      grid: {
        vertLines: { color: "#1f2937" },
        horzLines: { color: "#1f2937" },
      },
      crosshair: {
        mode: 1,
      },
      rightPriceScale: {
        borderColor: "#374151",
      },
      timeScale: {
        borderColor: "#374151",
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    // Add a line series for divergence connector (initially empty)
    const divergenceLine = chart.addSeries(LineSeries, {
      color: '#f59e0b',
      lineWidth: 2,
      priceLineVisible: false,
    });

    chartRef.current = chart;
    candlestickSeriesRef.current = candlestickSeries;
    divLineRef.current = divergenceLine;

    // Handle window resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
      }
    };
  }, []);

  // Update chart when data changes
  useEffect(() => {
    if (!candlestickSeriesRef.current || !data || data.length === 0) return;

    // Prepare candlestick data
    let firstTimeLogged = false;
    // Build parsed candles with original indices so we can lookup by divergence indices later
    const parsedCandles = data
      .map((d, index) => {
        const open = getValue(d, ['open', 'Open', 'OPEN']);
        const high = getValue(d, ['high', 'High', 'HIGH']);
        const low = getValue(d, ['low', 'Low', 'LOW']);
        const close = getValue(d, ['close', 'Close', 'CLOSE']);
        const time = getValue(d, ['time', 'Time', 'TIME', 'time_string', 'datetime', 'date']);
        
        if (open != null && high != null && low != null && close != null && time != null) {
          const parsedTime = parseTime(time);
          if (!firstTimeLogged && index === 0) {
            console.log("First candlestick time:", { original: time, parsed: parsedTime, type: typeof parsedTime });
            firstTimeLogged = true;
          }
          return {
            originalIndex: index,
            time: parsedTime,
            open: Number(open),
            high: Number(high),
            low: Number(low),
            close: Number(close),
          };
        }
        return null;
      })
      .filter((item): item is { originalIndex: number; time: Time; open: number; high: number; low: number; close: number } => item !== null)
      .sort((a, b) => timeToNumber(a.time) - timeToNumber(b.time));

    // Prepare data for the candlestick series (without originalIndex)
    const candlestickData = parsedCandles.map(({ time, open, high, low, close }) => ({ time, open, high, low, close }));

    console.log("Candlestick data prepared:", candlestickData.length, "items");
    if (candlestickData.length > 0) {
      console.log("First candlestick item:", candlestickData[0]);
    }

    // Update chart
    if (candlestickSeriesRef.current && candlestickData.length > 0) {
      try {
        candlestickSeriesRef.current.setData(candlestickData);
        chartRef.current?.timeScale().fitContent();
        console.log("Candlestick chart updated successfully");
      } catch (error) {
        console.error("Error updating candlestick chart:", error);
      }
    }

  }, [data]);

  // Effect to update divergence connector whenever data or activeDivergence changes
  useEffect(() => {
    if (!divLineRef.current) return;

    if (!activeDivergence || !data || data.length === 0) {
      try {
        divLineRef.current.setData([]);
      } catch (err) {
        // ignore
      }
      return;
    }

    const { prefixIndex, suffixIndex, type } = activeDivergence;

    // Ensure indices are valid
    if (prefixIndex == null || suffixIndex == null) {
      divLineRef.current.setData([]);
      return;
    }

    if (prefixIndex < 0 || suffixIndex < 0 || prefixIndex >= data.length || suffixIndex >= data.length) {
      divLineRef.current.setData([]);
      return;
    }

    // Find parsed candle entries by original index (the API's divergence indices refer to the original data array)
    const parsedCandles = data
      .map((d, index) => {
        const open = getValue(d, ['open', 'Open', 'OPEN']);
        const high = getValue(d, ['high', 'High', 'HIGH']);
        const low = getValue(d, ['low', 'Low', 'LOW']);
        const close = getValue(d, ['close', 'Close', 'CLOSE']);
        const time = getValue(d, ['time', 'Time', 'TIME', 'time_string', 'datetime', 'date']);
        if (open != null && high != null && low != null && close != null && time != null) {
          return {
            originalIndex: index,
            time: parseTime(time),
            open: Number(open),
            high: Number(high),
            low: Number(low),
            close: Number(close),
          };
        }
        return null;
      })
      .filter((x): x is { originalIndex: number; time: Time; open: number; high: number; low: number; close: number } => x !== null)
      .sort((a, b) => timeToNumber(a.time) - timeToNumber(b.time));

    const p1 = parsedCandles.find(c => c.originalIndex === prefixIndex);
    const p2 = parsedCandles.find(c => c.originalIndex === suffixIndex);

    if (!p1 || !p2) {
      divLineRef.current.setData([]);
      return;
    }

    const t1raw = p1.time;
    const t2raw = p2.time;
    // choose price points: low for bullish, high for bearish
    const c1raw = type === 'bullish' ? p1.low : p1.high;
    const c2raw = type === 'bullish' ? p2.low : p2.high;

    if (t1raw == null || t2raw == null || c1raw == null || c2raw == null) {
      divLineRef.current.setData([]);
      return;
    }

    // `t1raw` and `t2raw` are already parsed `Time` values; use them directly
    const t1 = t1raw as Time;
    const t2 = t2raw as Time;
    const v1 = Number(c1raw);
    const v2 = Number(c2raw);

    // choose color by divergence type
    const color = type === 'bullish' ? '#22c55e' : type === 'bearish' ? '#ef4444' : '#f59e0b';
    try {
      // try to apply color option
      // @ts-ignore - applyOptions may exist on series
      divLineRef.current.applyOptions && divLineRef.current.applyOptions({ color });
    } catch (err) {
      // ignore
    }

    const normalizeTime = (t: Time): string | number => {
      if (typeof t === 'string' || typeof t === 'number') return t;
      // fallback for BusinessDay-like objects: convert to sortable number
      return timeToNumber(t as any);
    };

    try {
      divLineRef.current.setData([
        { time: normalizeTime(t1), value: v1 },
        { time: normalizeTime(t2), value: v2 },
      ] as any);
    } catch (err) {
      console.error('Failed to set divergence line data:', err);
    }
  }, [data, activeDivergence]);

  return (
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
        ref={chartContainerRef} 
        style={{ 
          width: "100%", 
          minHeight: "500px",
          position: "relative"
        }} 
      />
    </div>
  );
}

