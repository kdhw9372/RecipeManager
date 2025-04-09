import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  Container,
  Flex,
  Grid,
  Heading,
  IconButton,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalFooter,
  ModalBody,
  ModalCloseButton,
  Text,
  useDisclosure,
  useToast,
  Select,
  NumberInput,
  NumberInputField,
  NumberInputStepper,
  NumberIncrementStepper,
  NumberDecrementStepper,
} from '@chakra-ui/react';
import { FaChevronLeft, FaChevronRight, FaEllipsisV, FaPlus, FaShoppingCart } from 'react-icons/fa';
import api from '../services/api';
import RecipeSearch from '../components/RecipeSearch';

const mealTypes = [
  { id: 'breakfast', name: 'Frühstück' },
  { id: 'lunch', name: 'Mittagessen' },
  { id: 'dinner', name: 'Abendessen' },
  { id: 'snack', name: 'Snack' },
];

const MealPlanCalendar = () => {
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();
  
  const [currentDate, setCurrentDate] = useState(new Date());
  const [mealPlan, setMealPlan] = useState({});
  const [loading, setLoading] = useState(true);
  
  // Modal-State
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedMealType, setSelectedMealType] = useState(mealTypes[0].id);
  const [selectedRecipe, setSelectedRecipe] = useState(null);
  const [servings, setServings] = useState(2);
  const [notes, setNotes] = useState('');
  
  // Erster Tag der aktuellen Woche (Montag)
  const getFirstDayOfWeek = (date) => {
    const day = date.getDay();
    const diff = date.getDate() - day + (day === 0 ? -6 : 1); // Anpassen für Sonntag als ersten Tag
    return new Date(date.setDate(diff));
  };
  
  // Die Tage der aktuellen Woche
  const getDaysOfWeek = (firstDay) => {
    const days = [];
    for (let i = 0; i < 7; i++) {
      const day = new Date(firstDay);
      day.setDate(day.getDate() + i);
      days.push(day);
    }
    return days;
  };
  
  const firstDayOfWeek = getFirstDayOfWeek(new Date(currentDate));
  const daysOfWeek = getDaysOfWeek(firstDayOfWeek);
  
  // Formatierung für API-Anfragen
  const formatDateForApi = (date) => {
    return date.toISOString().split('T')[0];
  };
  
  // Laden des Speiseplans
  useEffect(() => {
    const fetchMealPlan = async () => {
      try {
        const startDate = formatDateForApi(daysOfWeek[0]);
        const endDate = formatDateForApi(daysOfWeek[6]);
        
        const response = await api.get(`/meal-plans?start_date=${startDate}&end_date=${endDate}`);
        
        // Organisieren der Mahlzeiten nach Datum und Mahlzeitentyp
        const organized = {};
        response.data.forEach(meal => {
          const date = meal.date;
          if (!organized[date]) {
            organized[date] = {};
          }
          organized[date][meal.meal_type] = meal;
        });
        
        setMealPlan(organized);
      } catch (error) {
        toast({
          title: 'Fehler beim Laden des Speiseplans',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
      } finally {
        setLoading(false);
      }
    };
    
    fetchMealPlan();
  }, [daysOfWeek, toast]);
  
  // Navigation zur vorherigen/nächsten Woche
  const previousWeek = () => {
    const newDate = new Date(currentDate);
    newDate.setDate(newDate.getDate() - 7);
    setCurrentDate(newDate);
  };
  
  const nextWeek = () => {
    const newDate = new Date(currentDate);
    newDate.setDate(newDate.getDate() + 7);
    setCurrentDate(newDate);
  };
  
  // Modal öffnen zum Hinzufügen einer Mahlzeit
  const openAddMealModal = (date, mealType) => {
    setSelectedDate(date);
    setSelectedMealType(mealType);
    setSelectedRecipe(null);
    setServings(2);
    setNotes('');
    onOpen();
  };
  
  // Mahlzeit speichern
  const saveMeal = async () => {
    if (!selectedRecipe) {
      toast({
        title: 'Bitte wählen Sie ein Rezept aus',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    
    try {
      const dateStr = formatDateForApi(selectedDate);
      
      // Prüfen, ob bereits ein Eintrag für diese Kombination existiert
      const existingMeal = mealPlan[dateStr]?.[selectedMealType];
      
      const mealData = {
        date: dateStr,
        meal_type: selectedMealType,
        recipe_id: selectedRecipe.id,
        servings: servings,
        notes: notes,
      };
      
      let response;
      if (existingMeal) {
        // Vorhandene Mahlzeit aktualisieren
        response = await api.put(`/meal-plans/${existingMeal.id}`, mealData);
      } else {
        // Neue Mahlzeit erstellen
        response = await api.post('/meal-plans', mealData);
      }
      
      // Aktualisieren des lokalen Zustands
      const updatedMealPlan = { ...mealPlan };
      if (!updatedMealPlan[dateStr]) {
        updatedMealPlan[dateStr] = {};
      }
      updatedMealPlan[dateStr][selectedMealType] = response.data;
      
      setMealPlan(updatedMealPlan);
      onClose();
      
      toast({
        title: 'Mahlzeit gespeichert',
        status: 'success',
        duration: 3000,
        isClosable: true,
      });
    } catch (error) {
      toast({
        title: 'Fehler beim Speichern der Mahlzeit',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    }
  };
  
  // Mahlzeit entfernen
  const removeMeal = async (mealId) => {
    if (window.confirm('Möchten Sie diese Mahlzeit wirklich entfernen?')) {
      try {
        await api.delete(`/meal-plans/${mealId}`);
        
        // Aktualisieren des lokalen Zustands
        const updatedMealPlan = { ...mealPlan };
        
        // Durchlaufen aller Daten und Mahlzeitentypen, um den Eintrag zu finden und zu entfernen
        Object.keys(updatedMealPlan).forEach(date => {
          Object.keys(updatedMealPlan[date]).forEach(mealType => {
            if (updatedMealPlan[date][mealType].id === mealId) {
              delete updatedMealPlan[date][mealType];
            }
          });
        });
        
        setMealPlan(updatedMealPlan);
        
        toast({
          title: 'Mahlzeit entfernt',
          status: 'success',
          duration: 3000,
          isClosable: true,
        });
      } catch (error) {
        toast({
          title: 'Fehler beim Entfernen der Mahlzeit',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
      }
    }
  };
  
  // Einkaufsliste für die Woche generieren
  const generateShoppingList = async () => {
    try {
      const startDate = formatDateForApi(daysOfWeek[0]);
      const endDate = formatDateForApi(daysOfWeek[6]);
      
      await api.post('/shopping-lists/generate', {
        start_date: startDate,
        end_date: endDate,
        name: `Einkaufsliste ${startDate} bis ${endDate}`
      });
      
      toast({
        title: 'Einkaufsliste erstellt',
        description: 'Die Einkaufsliste wurde erfolgreich erstellt.',
        status: 'success',
        duration: 3000,
        isClosable: true,
      });
    } catch (error) {
      toast({
        title: 'Fehler beim Erstellen der Einkaufsliste',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    }
  };
  
  // Formatierung des Datums für die Anzeige
  const formatDate = (date) => {
    return date.toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric', month: 'numeric' });
  };
  
  // Prüfen, ob ein Datum dem heutigen Datum entspricht
  const isToday = (date) => {
    const today = new Date();
    return date.getDate() === today.getDate() &&
      date.getMonth() === today.getMonth() &&
      date.getFullYear() === today.getFullYear();
  };
  
  return (
    <Container maxW="container.xl" py={6}>
      <Box mb={6}>
        <Flex justify="space-between" align="center" mb={4}>
          <Heading as="h1" size="xl">Menüplaner</Heading>
          <Flex gap={2}>
            <Button
              leftIcon={<FaShoppingCart />}
              colorScheme="green"
              onClick={generateShoppingList}
            >
              Einkaufsliste erstellen
            </Button>
          </Flex>
        </Flex>
        
        {/* Wochennavigation */}
        <Flex justify="space-between" align="center" mb={4}>
          <IconButton
            icon={<FaChevronLeft />}
            onClick={previousWeek}
            aria-label="Vorherige Woche"
          />
          <Text fontSize="lg" fontWeight="bold">
            {firstDayOfWeek.toLocaleDateString('de-DE', { day: 'numeric', month: 'long' })} - {
              new Date(firstDayOfWeek.getTime() + 6 * 24 * 60 * 60 * 1000)
                .toLocaleDateString('de-DE', { day: 'numeric', month: 'long', year: 'numeric' })
            }
          </Text>
          <IconButton
            icon={<FaChevronRight />}
            onClick={nextWeek}
            aria-label="Nächste Woche"
          />
        </Flex>
        
        {/* Wochenkalender */}
        <Grid templateColumns="repeat(8, 1fr)" gap={2}>
          {/* Spaltenüberschriften für Mahlzeitentypen */}
          <Box />
          {daysOfWeek.map((day, index) => (
            <Box
              key={index}
              p={2}
              textAlign="center"
              fontWeight="bold"
              bg={isToday(day) ? 'blue.100' : 'gray.100'}
              borderRadius="md"
            >
              {formatDate(day)}
            </Box>
          ))}
          
          {/* Zeilen für die Mahlzeitentypen */}
          {mealTypes.map(mealType => (
            <React.Fragment key={mealType.id}>
              <Box p={2} fontWeight="bold">
                {mealType.name}
              </Box>
              
              {daysOfWeek.map((day, dayIndex) => {
                const dateStr = formatDateForApi(day);
                const meal = mealPlan[dateStr]?.[mealType.id];
                
                return (
                  <Box
                    key={dayIndex}
                    p={2}
                    bg="white"
                    borderWidth={1}
                    borderRadius="md"
                    minHeight="80px"
                  >
                    {meal ? (
                      <Flex direction="column" height="100%">
                        <Flex justify="space-between" align="center">
                          <Text fontWeight="bold" noOfLines={1}>
                            {meal.recipe.title}
                          </Text>
                          <Menu>
                            <MenuButton
                              as={IconButton}
                              icon={<FaEllipsisV />}
                              variant="ghost"
                              size="sm"
                              aria-label="Optionen"
                            />
                            <MenuList>
                              <MenuItem
                                onClick={() => {
                                  setSelectedDate(day);
                                  setSelectedMealType(mealType.id);
                                  setSelectedRecipe(meal.recipe);
                                  setServings(meal.servings);
                                  setNotes(meal.notes || '');
                                  onOpen();
                                }}
                              >
                                Bearbeiten
                              </MenuItem>
                              <MenuItem
                                onClick={() => removeMeal(meal.id)}
                              >
                                Entfernen
                              </MenuItem>
                            </MenuList>
                          </Menu>
                        </Flex>
                        <Text fontSize="sm">Portionen: {meal.servings}</Text>
                        {meal.notes && (
                          <Text fontSize="xs" color="gray.600" mt={1} noOfLines={2}>
                            {meal.notes}
                          </Text>
                        )}
                      </Flex>
                    ) : (
                      <Flex
                        height="100%"
                        justify="center"
                        align="center"
                      >
                        <IconButton
                          icon={<FaPlus />}
                          size="sm"
                          variant="ghost"
                          aria-label="Mahlzeit hinzufügen"
                          onClick={() => openAddMealModal(day, mealType.id)}
                        />
                      </Flex>
                    )}
                  </Box>
                );
              })}
            </React.Fragment>
          ))}
        </Grid>
      </Box>
      
      {/* Modal zum Hinzufügen/Bearbeiten einer Mahlzeit */}
      <Modal isOpen={isOpen} onClose={onClose} size="lg">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>
            {selectedRecipe ? 'Mahlzeit bearbeiten' : 'Mahlzeit hinzufügen'}
          </ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <Flex direction="column" gap={4}>
              <Box>
                <Text fontWeight="bold" mb={2}>Datum & Mahlzeit</Text>
                <Flex gap={4}>
                  <Text>{selectedDate?.toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' })}</Text>
                  <Select
                    value={selectedMealType}
                    onChange={(e) => setSelectedMealType(e.target.value)}
                  >
                    {mealTypes.map(type => (
                      <option key={type.id} value={type.id}>
                        {type.name}
                      </option>
                    ))}
                  </Select>
                </Flex>
              </Box>
              
              <Box>
                <Text fontWeight="bold" mb={2}>Rezept auswählen</Text>
                <RecipeSearch
                  selectedRecipe={selectedRecipe}
                  onSelectRecipe={setSelectedRecipe}
                />
              </Box>
              
              