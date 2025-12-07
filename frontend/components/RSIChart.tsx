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
}

export default function RSIChart({ data }: RSIChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const overboughtLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const oversoldLineRef = useRef<ISeriesApi<"Line"> | null>(null);

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

    // Prepare RSI data
    let firstRSITimeLogged = false;
    const rsiData = data
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
            time: parsedTime,
            value: Number(rsi),
          };
        }
        return null;
      })
      .filter((item): item is { time: Time; value: number } => item !== null)
      .sort((a, b) => timeToNumber(a.time) - timeToNumber(b.time));

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

