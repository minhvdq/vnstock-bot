import { useEffect, useRef } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, LineSeries, Time } from "lightweight-charts";
import { parseTime, timeToNumber, getValue } from "./utils";

type StockData = {
  time: string | number;
  RSI?: number;
  [key: string]: string | number | null | undefined;
};

interface RSIChartProps {
  data: StockData[];
  activeDivergence?: { prefixIndex: number; suffixIndex: number; type: string } | null;
}

export default function RSIChart({ data, activeDivergence }: RSIChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const overboughtLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const oversoldLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const divLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const parsedRsiRef = useRef<Array<{ originalIndex: number; time: Time; value: number }> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Initialize RSI chart
    const rsiChart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#020617" },
        textColor: "#e5e7eb",
      },
      width: chartContainerRef.current.clientWidth,
      height: 300,
      grid: {
        vertLines: { color: "#1f2937" },
        horzLines: { color: "#1f2937" },
      },
      crosshair: {
        mode: 1,
      },
      rightPriceScale: {
        borderColor: "#374151",
        scaleMargins: {
          top: 0.1,
          bottom: 0.1,
        },
      },
      timeScale: {
        borderColor: "#374151",
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const rsiSeries = rsiChart.addSeries(LineSeries, {
      color: "#3b82f6",
      lineWidth: 2,
    });

    // Add RSI reference lines (70 = overbought, 30 = oversold)
    const overboughtLine = rsiChart.addSeries(LineSeries, {
      color: "#ef4444",
      lineWidth: 1,
      lineStyle: 2, // Dashed line
      priceFormat: {
        type: "price",
        precision: 1,
        minMove: 0.1,
      },
    });

    const oversoldLine = rsiChart.addSeries(LineSeries, {
      color: "#22c55e",
      lineWidth: 1,
      lineStyle: 2, // Dashed line
      priceFormat: {
        type: "price",
        precision: 1,
        minMove: 0.1,
      },
    });

    // Set price scale to show 0-100 range for RSI
    rsiChart.priceScale("right").applyOptions({
      scaleMargins: {
        top: 0.05,
        bottom: 0.05,
      },
    });

    chartRef.current = rsiChart;
    rsiSeriesRef.current = rsiSeries;
    overboughtLineRef.current = overboughtLine;
    oversoldLineRef.current = oversoldLine;

    const divergenceLine = rsiChart.addSeries(LineSeries, {
      color: '#f59e0b',
      lineWidth: 2,
      priceLineVisible: false,
    });
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
    if (!rsiSeriesRef.current || !data || data.length === 0) return;

    // Prepare RSI data (keep original indices so divergences reference correctly)
    let firstRSITimeLogged = false;
    const parsedRsi = data
      .map((d, index) => {
        const rsi = getValue(d, ['RSI', 'rsi']);
        const time = getValue(d, ['time', 'Time', 'TIME', 'time_string', 'datetime', 'date']);

        if (rsi != null && !isNaN(Number(rsi)) && time != null) {
          const parsedTime = parseTime(time);
          if (!firstRSITimeLogged && index === 0) {
            console.log("First RSI time:", { original: time, parsed: parsedTime, type: typeof parsedTime });
            firstRSITimeLogged = true;
          }
          return {
            originalIndex: index,
            time: parsedTime,
            value: Number(rsi),
          };
        }
        return null;
      })
      .filter((item): item is { originalIndex: number; time: Time; value: number } => item !== null)
      .sort((a, b) => timeToNumber(a.time) - timeToNumber(b.time));

    parsedRsiRef.current = parsedRsi;
    const rsiData = parsedRsi.map(({ time, value }) => ({ time, value }));

    console.log("RSI data prepared:", rsiData.length, "items");
    if (rsiData.length > 0) {
      console.log("First RSI item:", rsiData[0]);
    }

    // Update chart
    if (rsiSeriesRef.current && rsiData.length > 0) {
      try {
        rsiSeriesRef.current.setData(rsiData);
        chartRef.current?.timeScale().fitContent();
        console.log("RSI chart updated successfully");
        
        // Update reference lines
        const minTime = rsiData[0].time;
        const maxTime = rsiData[rsiData.length - 1].time;
        
        if (overboughtLineRef.current) {
          overboughtLineRef.current.setData([
            { time: minTime, value: 70 },
            { time: maxTime, value: 70 },
          ]);
        }
        
        if (oversoldLineRef.current) {
          oversoldLineRef.current.setData([
            { time: minTime, value: 30 },
            { time: maxTime, value: 30 },
          ]);
        }
      } catch (error) {
        console.error("Error updating RSI chart:", error);
      }
    }
  }, [data]);

  // Update divergence connector on RSI whenever data or active divergence changes
  useEffect(() => {
    if (!divLineRef.current) return;

    if (!activeDivergence || !data || data.length === 0) {
      try { divLineRef.current.setData([]); } catch (e) {}
      return;
    }

    const { prefixIndex, suffixIndex, type } = activeDivergence;
    if (prefixIndex == null || suffixIndex == null) {
      divLineRef.current.setData([]);
      return;
    }

    if (prefixIndex < 0 || suffixIndex < 0 || prefixIndex >= data.length || suffixIndex >= data.length) {
      divLineRef.current.setData([]);
      return;
    }

    // use parsed RSI points (match by originalIndex so indices from backend are respected)
    const parsed = parsedRsiRef.current;
    if (!parsed) {
      divLineRef.current.setData([]);
      return;
    }

    const p1 = parsed.find(p => p.originalIndex === prefixIndex);
    const p2 = parsed.find(p => p.originalIndex === suffixIndex);

    if (!p1 || !p2) {
      divLineRef.current.setData([]);
      return;
    }

    const t1 = p1.time;
    const t2 = p2.time;
    const v1 = p1.value;
    const v2 = p2.value;

    const color = type === 'bullish' ? '#22c55e' : type === 'bearish' ? '#ef4444' : '#f59e0b';
    try { divLineRef.current.applyOptions && divLineRef.current.applyOptions({ color }); } catch(e) {}
    const normalizeTime = (t: Time): string | number => {
      if (typeof t === 'string' || typeof t === 'number') return t;
      return timeToNumber(t as any);
    };

    try {
      divLineRef.current.setData([
        { time: normalizeTime(t1), value: v1 },
        { time: normalizeTime(t2), value: v2 },
      ] as any);
    } catch (err) {
      console.error('Failed to set RSI divergence line:', err);
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
        RSI Indicator
      </h2>
      <div 
        ref={chartContainerRef} 
        style={{ 
          width: "100%", 
          minHeight: "300px",
          position: "relative"
        }} 
      />
    </div>
  );
}

