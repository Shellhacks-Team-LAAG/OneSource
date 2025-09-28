import React from "react";
import { BrowserRouter as Router, Routes, Route, Link } from "react-router-dom";
import AskPage from "./pages/AskPage";
import ConnectionsPage from "./pages/ConnectionsPage";

function App() {
  return (
    <Router>
      <div className="p-4">
        {/* Simple NavBar */}
        <nav className="mb-4 space-x-4">
          <Link to="/" className="text-blue-500 underline">Ask</Link>
          <Link to="/connections" className="text-blue-500 underline">Connections</Link>
        </nav>

        {/* Routes */}
        <Routes>
          <Route path="/" element={<AskPage />} />
          <Route path="/connections" element={<ConnectionsPage />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
