import React, { useEffect, useState } from "react";
import io from "socket.io-client";
import axios from "axios";
import { Table, Tag, Button, Card, Layout, Typography, Row, Col, DatePicker, Space } from "antd";
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis } from "recharts";
import { notification } from "antd";

const { Header, Content } = Layout;
const { Title } = Typography;
const { RangePicker } = DatePicker;
const socket = io("http://127.0.0.1:5000");

function App() {
  const [transactions, setTransactions] = useState([]);
  const [fraudSummary, setFraudSummary] = useState(null);
  const [fraudData, setFraudData] = useState([]);
  const [highRiskCountryData, setHighRiskCountryData] = useState([]);
  const [dateRange, setDateRange] = useState([]);
  const [pageSize, setPageSize] = useState(5);

  useEffect(() => {
    fetchTransactions();

    socket.on("fraud_alert", (alert) => {
      setTransactions((prevTransactions) => {
        const updatedTransactions = [alert.data, ...prevTransactions];
        processFraudData(updatedTransactions);
        processHighRiskCountryData(updatedTransactions);
        return updatedTransactions;
      });
    });

    return () => {
      socket.off("fraud_alert");
    };
  }, []);

  const fetchTransactions = () => {
    axios
      .get("http://127.0.0.1:5000/fraud_cases")
      .then((response) => {
        setTransactions(response.data);
        processFraudData(response.data);
        processHighRiskCountryData(response.data);
      })
      .catch((error) => console.error("Error fetching transactions", error));
  };

  // ✅ Process fraud data for the donut chart (excluding "No Risk")
  const processFraudData = (data) => {
    const riskCounts = data.reduce((acc, transaction) => {
      if (transaction.risk_level !== "No Risk") {
        acc[transaction.risk_level] = (acc[transaction.risk_level] || 0) + 1;
      }
      return acc;
    }, {});

    const totalCases = Object.values(riskCounts).reduce((sum, count) => sum + count, 0);
    const chartData = Object.keys(riskCounts).map((risk) => ({
      name: risk,
      value: riskCounts[risk],
      percentage: ((riskCounts[risk] / totalCases) * 100).toFixed(1) + "%",
    }));

    setFraudData(chartData);
  };

  // ✅ Process high-risk fraud cases by country (Display All Countries)
  const processHighRiskCountryData = (data) => {
    const highRiskCases = data.filter((transaction) => transaction.risk_level === "High Risk");
  
    const countryCounts = highRiskCases.reduce((acc, transaction) => {
      acc[transaction.country] = (acc[transaction.country] || 0) + 1;
      return acc;
    }, {});
  
    // Find the maximum count of high-risk cases in a country
    const maxCases = Math.max(...Object.values(countryCounts));
  
    // Generate color shades based on the highest count
    const allCountries = Object.entries(countryCounts).map(([country, count]) => {
      const intensity = count / maxCases; // Normalize intensity between 0 and 1
      const redValue = Math.floor(255 - intensity * 155); // Darker red for higher cases
  
      return {
        name: country,
        x: Math.random() * 10, // Random x-position to avoid overlapping
        y: count + 10, // Number of high-risk cases
        z: count * 3, // Bubble size
        color: count === maxCases ? "#B82132" : "#FFA09B", // Adjust red intensity dynamically
      };
    });
  
    setHighRiskCountryData(allCountries);
  };
  

  const generateFraudSummary = async (clientId) => {
    try {
      const response = await axios.post("http://127.0.0.1:5000/generate_summary", { client_id: clientId });

      if (response.data.error) {
        console.error("Fraud Summary Error:", response.data.error);
        setFraudSummary({ client_id: clientId, risk_level: "Unknown", reason: "No fraud detected or data missing." });
      } else {
        setFraudSummary(response.data);
      }
    } catch (error) {
      console.error("Error generating fraud summary", error);
    }
  };

  const generateReport = async () => {
    if (!dateRange.length) {
      alert("Please select a date range.");
      return;
    }

    const startDate = dateRange[0].format("YYYY-MM-DD");
    const endDate = dateRange[1].format("YYYY-MM-DD");

    try {
      const response = await axios.post("http://127.0.0.1:5000/generate_report", {
        start_date: startDate,
        end_date: endDate,
      }, { responseType: 'blob' });

      const fileURL = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = fileURL;
      link.setAttribute("download", "fraud_report.pdf");
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error) {
      console.error("Error generating report", error);
    }
  };

  const columns = [
    {
      title: "Client ID",
      dataIndex: "client_id",
      key: "client_id",
      align: "center",
      sorter: (a, b) => a.client_id.localeCompare(b.client_id), // Sort alphabetically
      render: (clientId) => (
        <Button type="link" onClick={() => generateFraudSummary(clientId)}>
          {clientId}
        </Button>
      ),
    },
    { 
      title: "Deposit Amount", 
      dataIndex: "deposit_amount", 
      key: "deposit_amount", 
      align: "center",
      sorter: (a, b) => a.deposit_amount - b.deposit_amount, // Sort numerically
    },
    { 
      title: "Withdrawal Amount", 
      dataIndex: "withdrawal_amount", 
      key: "withdrawal_amount", 
      align: "center",
      sorter: (a, b) => a.withdrawal_amount - b.withdrawal_amount, // Sort numerically
    },
    {
      title: "Detection Time",
      dataIndex: "detection_timestamp",
      key: "detection_timestamp",
      align: "center",
      defaultSortOrder: "descend",
      sorter: (a, b) => new Date(a.detection_timestamp) - new Date(b.detection_timestamp), // Sort by date
    },
    {
      title: "Risk Level",
      dataIndex: "risk_level",
      key: "risk_level",
      align: "center",
      sorter: (a, b) => {
        const riskOrder = { "High Risk": 1, "Medium Risk": 2, "Low Risk": 3, "No Risk": 4 };
        return riskOrder[a.risk_level] - riskOrder[b.risk_level]; // Sort by risk level priority
      },
      render: (level) => (
        <Tag color={level === "High Risk" ? "#A31D1D" : level === "Medium Risk" ? "#F96E2A" : level === "Low Risk" ? "#FFB200" : "#28A745"}>
          {level}
        </Tag>
      ),
    },
    {
      title: "Status",  // ✅ New column for status
      key: "status",
      align: "center",
      sorter: (a, b) => {
        const statusOrder = { "Locked": 1, "Review": 2, "Monitor": 3, "Safe": 4 };
        return statusOrder[getStatus(a.risk_level)] - statusOrder[getStatus(b.risk_level)];
      },
      render: (_, record) => {
        const status = getStatus(record.risk_level);
        return (
          <Tag color={status === "Locked" ? "#A31D1D" : status === "Review" ? "#F96E2A" : status === "Monitor" ? "#FFB200" : "#28A745"}>
            {status}
          </Tag>
        );
      },
    },
  ];
  
  // ✅ Function to map risk level to status
  const getStatus = (riskLevel) => {
    switch (riskLevel) {
      case "High Risk":
        return "Locked";
      case "Medium Risk":
        return "Review";
      case "Low Risk":
        return "Monitor";
      case "No Risk":
        return "Safe";
      default:
        return "Unknown";
    }
  };
  
  

  return (
    <Layout>
      <Header style={{ textAlign: "center", background: "#001529", padding: "10px" }}>
        <Title level={2} style={{ color: "#fff", margin: 0 }}>
          Fraud Detection System
        </Title>
      </Header>

      <Content style={{ padding: "20px", display: "flex", flexDirection: "column", alignItems: "center" }}>
        <Row gutter={[16, 16]} style={{ width: "100%", marginBottom: "20px" }}>
          <Col xs={24} md={12} style={{ flex: 1, minWidth: "400px" }}>
            <Card title="Fraud Cases by Risk Level" headStyle={{ fontSize: "25px", textAlign: "center", fontWeight: "bold" }}>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                <Legend layout="horizontal" verticalAlign="top" align="center" />
                  <Pie data={fraudData} cx="50%" cy="50%" innerRadius={50} outerRadius={90} dataKey="value">
                    {fraudData.map((entry, index) => (
                      <Cell key={`cell-${index}`} 
                        fill={
                          entry.name === "High Risk" ? "#A31D1D" : 
                          entry.name === "Medium Risk" ? "#F96E2A" : 
                          entry.name === "Low Risk" ? "#FFB200" : 
                          "#FADA7A"} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value, name, props) => [`${props.payload.percentage}`, name]} />
                </PieChart>
              </ResponsiveContainer>
            </Card>
          </Col>

          <Col xs={24} md={12} style={{ flex: 1, minWidth: "400px" }}>
            <Card 
              title={
                <div style={{ textAlign: "center" }}>
                  <span style={{ fontSize: "25px", fontWeight: "bold" }}>
                    High Risk Fraud Cases by Country
                  </span>
                  <br />
                  <span style={{ fontSize: "12px", color: "#666" }}>
                    Bubble size indicates the proportion of high-risk fraud cases in each country.
                  </span>
                </div>
              }
              headStyle={{ textAlign: "center" }}>
              <ResponsiveContainer width="100%" height={300}>
                <ScatterChart>
                  <XAxis dataKey="name" />
                  <YAxis dataKey="y" tick={false} axisLine={false}/>
                  <ZAxis dataKey="z" range={[50, 3000]} />
                  <Scatter data={highRiskCountryData}>
                    {highRiskCountryData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Scatter>
                  <Tooltip 
                    cursor={{ strokeDasharray: '3 3' }} 
                    content={({ payload }) => {
                      if (payload && payload.length) {
                        const { name, y } = payload[0].payload; 
                        const totalHighRiskCases = highRiskCountryData.reduce((sum, d) => sum + d.y, 0);
                        const percentage = ((y / totalHighRiskCases) * 100).toFixed(2);
                        return (
                          <div style={{ backgroundColor: "#fff", padding: "10px", border: "1px solid #ccc", borderRadius: "5px" }}>
                            <p><strong>Country:</strong> {name}</p>
                            <p><strong>Percentage:</strong> {percentage}%</p>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                </ScatterChart>
              </ResponsiveContainer>
            </Card>
          </Col> 
        </Row>

            <Card title="Fraud Risk Summary" 
              style={{ textAlign: "center", width: "100%" }}
              headStyle={{ textAlign: "center", fontSize: "25px", fontWeight: "bold" }}>
              {fraudSummary ? (
                <>
                  <p style={{ fontSize: "18px" }}>
                    <strong>Client ID:</strong> {fraudSummary.client_id}
                  </p>
                  <p style={{ fontSize: "18px" }}>
                    <strong>Risk Level:</strong> {fraudSummary.risk_level}
                  </p>
                  <p style={{ fontSize: "18px" }}>
                    <strong>Reason:</strong> {fraudSummary.reason}
                  </p>
                </>
              ) : (
                <p style={{ textAlign: "center", fontSize: "18px", color: "#666"}}>
                  Click a Client ID to generate a personalized fraud summary.
                </p>
              )}
            </Card>

            {/* ✅ Generate Report Section */}
            <Card title="Generate Report" 
              style={{ textAlign: "center", width: "100%", marginTop: "20px" }}
              headStyle={{ textAlign: "center", fontSize: "25px", fontWeight: "bold" }}>
              <Space direction="horizontal">
                <RangePicker format="DD/MM/YYYY" onChange={setDateRange} />
                <Button type="primary" style={{ backgroundColor: "#001529", color: "#fff", border: "1px solid #fff" }} onClick={generateReport}>
                  Generate Report
                </Button>
              </Space>
            </Card>

        <Card 
          title="Recent Transaction List" 
          style={{ marginTop: "20px", width: "100%" }}
          headStyle={{ textAlign: "center", fontSize: "25px", fontWeight: "bold" }}>
          <Table 
            dataSource={transactions} 
            columns={columns} 
            rowKey="id" 
            pagination={{ 
              pageSize: pageSize,
              showSizeChanger: true,
              pageSizeOptions: ["5", "10", "20", "50", "100"],
              onShowSizeChange: (current, size) => setPageSize(size) }} 
            style={{ marginTop: "20px", width: "100%" }} 
          />
        </Card>
      </Content>
    </Layout>
  );
}

export default App;
