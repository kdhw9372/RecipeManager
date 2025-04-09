import React, { useState, useEffect } from 'react';
import {
  Box,
  Flex,
  Text,
  Progress,
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
  CircularProgress,
  CircularProgressLabel,
  Badge,
  Stack,
  Heading,
  Icon,
  useColorModeValue,
} from '@chakra-ui/react';
import { FaCheckCircle, FaExclamationTriangle, FaSpinner, FaClock } from 'react-icons/fa';
import { format, formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';

import api from '../../services/api';

const ProcessingStatus = () => {
  const [processingData, setProcessingData] = useState({
    activeJobs: 0,
    completedJobs: 0,
    errorJobs: 0,
    pendingJobs: 0,
    recentBatches: [],
    processingSpeed: 0,  // PDFs pro Minute
    estimatedTimeRemaining: 0  // in Minuten
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await api.get('/processing/status');
        setProcessingData(response.data);
        setLoading(false);
      } catch (err) {
        setError('Fehler beim Laden des Verarbeitungsstatus');
        setLoading(false);
      }
    };

    fetchData();
    // Alle 30 Sekunden aktualisieren
    const interval = setInterval(fetchData, 30000);
    
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <Box p={4} borderWidth="1px" borderRadius="lg" bg={bgColor}>
        <Flex justify="center" align="center" height="200px">
          <CircularProgress isIndeterminate color="blue.300" />
        </Flex>
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={4} borderWidth="1px" borderRadius="lg" bg={bgColor}>
        <Flex direction="column" justify="center" align="center" height="200px">
          <Icon as={FaExclamationTriangle} color="orange.500" boxSize={10} mb={4} />
          <Text>{error}</Text>
        </Flex>
      </Box>
    );
  }

  // Berechnung des Gesamtfortschritts
  const totalJobs = processingData.activeJobs + processingData.completedJobs + 
                    processingData.errorJobs + processingData.pendingJobs;
  const progressPercentage = totalJobs > 0 
    