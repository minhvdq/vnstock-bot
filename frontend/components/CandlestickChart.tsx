import { useEffect, useRef } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, CandlestickSeries, Time } from "lightweight-charts";
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
}

export default function CandlestickChart({ data }: CandlestickChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

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

    chartRef.current = chart;
    candlestickSeriesRef.current = candlestickSeries;

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
    const candlestickData = data
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
            time: parsedTime,
            open: Number(open),
            high: Number(high),
            low: Number(low),
            close: Number(close),
          };
        }
        return null;
      })
      .filter((item): item is { time: Time; open: number; high: number; low: number; close: number } => item !== null)
      .sort((a, b) => timeToNumber(a.time) - timeToNumber(b.time));

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

