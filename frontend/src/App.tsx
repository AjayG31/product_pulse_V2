import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  AppBar,
  Box,
  Card,
  CardContent,
  Container,
  CssBaseline,
  ThemeProvider,
  Toolbar,
  Typography,
  createTheme,
} from "@mui/material";
import { BrowserRouter, Route, Routes } from "react-router";

const queryClient = new QueryClient();
const theme = createTheme({
  palette: {
    primary: { main: "#17324d" },
    background: { default: "#f4f7fa" },
  },
});

function FoundationPage() {
  return (
    <Container maxWidth="md" sx={{ py: 5 }}>
      <Typography component="h1" variant="h4" gutterBottom>
        Product quality monitoring
      </Typography>
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6">Application foundation</Typography>
          <Typography color="text.secondary">
            The application shell is ready. Product workflows will appear here as their approved
            milestones are implemented.
          </Typography>
        </CardContent>
      </Card>
    </Container>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <BrowserRouter>
          <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
            <AppBar position="static">
              <Toolbar>
                <Typography component="span" variant="h6">
                  ProductPulse
                </Typography>
              </Toolbar>
            </AppBar>
            <Routes>
              <Route path="/" element={<FoundationPage />} />
            </Routes>
          </Box>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

