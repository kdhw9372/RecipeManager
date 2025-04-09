import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Container,
  Divider,
  Flex,
  Heading,
  Image,
  List,
  ListItem,
  Spinner,
  Stack,
  Tag,
  Text,
  useToast,
  IconButton,
  NumberInput,
  NumberInputField,
  NumberInputStepper,
  NumberIncrementStepper,
  NumberDecrementStepper,
} from '@chakra-ui/react';
import { FaHeart, FaRegHeart, FaEdit, FaTrash, FaShoppingCart, FaPrint } from 'react-icons/fa';
import api from '../services/api';

const RecipeDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  
  const [recipe, setRecipe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [servings, setServings] = useState(0);
  
  useEffect(() => {
    const fetchRecipe = async () => {
      try {
        const response = await api.get(`/recipes/${id}`);
        setRecipe(response.data);
        setServings(response.data.servings);
      } catch (error) {
        toast({
          title: 'Fehler beim Laden des Rezepts',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
      } finally {
        setLoading(false);
      }
    };
    
    fetchRecipe();
  }, [id, toast]);
  
  const handleServingsChange = async (value) => {
    try {
      const response = await api.get(`/recipes/${id}/scale?servings=${value}`);
      setRecipe(response.data);
      setServings(value);
    } catch (error) {
      toast({
        title: 'Fehler beim Skalieren des Rezepts',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    }
  };
  
  const toggleFavorite = async () => {
    try {
      const response = await api.post(`/recipes/${id}/favorite`);
      setRecipe({ ...recipe, is_favorite: response.data.is_favorite });
    } catch (error) {
      toast({
        title: 'Fehler beim Ändern des Favoriten-Status',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    }
  };
  
  const addToShoppingList = async () => {
    try {
      await api.post(`/shopping-lists/add-recipe`, {
        recipe_id: id,
        servings: servings,
      });
      
      toast({
        title: 'Zutaten zur Einkaufsliste hinzugefügt',
        status: 'success',
        duration: 3000,
        isClosable: true,
      });
    } catch (error) {
      toast({
        title: 'Fehler beim Hinzufügen zur Einkaufsliste',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    }
  };
  
  const handleDelete = async () => {
    if (window.confirm('Möchten Sie dieses Rezept wirklich löschen?')) {
      try {
        await api.delete(`/recipes/${id}`);
        toast({
          title: 'Rezept gelöscht',
          status: 'success',
          duration: 3000,
          isClosable: true,
        });
        navigate('/recipes');
      } catch (error) {
        toast({
          title: 'Fehler beim Löschen des Rezepts',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
      }
    }
  };
  
  if (loading) {
    return (
      <Flex justify="center" align="center" height="50vh">
        <Spinner size="xl" />
      </Flex>
    );
  }
  
  if (!recipe) {
    return (
      <Container maxW="container.lg" py={6}>
        <Text>Rezept nicht gefunden.</Text>
      </Container>
    );
  }
  
  return (
    <Container maxW="container.lg" py={6}>
      <Stack spacing={6}>
        {/* Header mit Titel und Aktionen */}
        <Flex justify="space-between" align="center" wrap="wrap">
          <Heading as="h1" size="xl">
            {recipe.title}
          </Heading>
          <Stack direction="row" spacing={2}>
            <IconButton
              icon={recipe.is_favorite ? <FaHeart /> : <FaRegHeart />}
              colorScheme={recipe.is_favorite ? 'red' : 'gray'}
              aria-label="Als Favorit markieren"
              onClick={toggleFavorite}
            />
            <IconButton
              icon={<FaEdit />}
              colorScheme="blue"
              aria-label="Rezept bearbeiten"
              onClick={() => navigate(`/recipes/edit/${id}`)}
            />
            <IconButton
              icon={<FaTrash />}
              colorScheme="red"
              aria-label="Rezept löschen"
              onClick={handleDelete}
            />
            <IconButton
              icon={<FaPrint />}
              colorScheme="gray"
              aria-label="Rezept drucken"
              onClick={() => window.print()}
            />
          </Stack>
        </Flex>
        
        {/* Bild und Metadaten */}
        <Flex
          direction={{ base: 'column', md: 'row' }}
          gap={6}
        >
          {recipe.image_path && (
            <Box maxW={{ base: 'full', md: '400px' }}>
              <Image
                src={`/api/media/images/${recipe.image_path.split('/').pop()}`}
                alt={recipe.title}
                borderRadius="md"
                objectFit="cover"
                width="100%"
              />
            </Box>
          )}
          <Box flex="1">
            <Stack spacing={4}>
              {/* Kategorien */}
              <Flex gap={2} wrap="wrap">
                {recipe.categories && recipe.categories.map(category => (
                  <Tag key={category.id} size="md" colorScheme="blue">
                    {category.name}
                  </Tag>
                ))}
              </Flex>
              
              {/* Metadaten */}
              <Flex gap={6} wrap="wrap">
                {recipe.preparation_time && (
                  <Box>
                    <Text fontWeight="bold">Zubereitungszeit</Text>
                    <Text>{recipe.preparation_time} Min.</Text>
                  </Box>
                )}
                {recipe.cooking_time && (
                  <Box>
                    <Text fontWeight="bold">Kochzeit</Text>
                    <Text>{recipe.cooking_time} Min.</Text>
                  </Box>
                )}
                {recipe.difficulty && (
                  <Box>
                    <Text fontWeight="bold">Schwierigkeit</Text>
                    <Text>{recipe.difficulty}</Text>
                  </Box>
                )}
              </Flex>
              
              {/* Nährwerte */}
              {recipe.nutrition && (
                <Box>
                  <Text fontWeight="bold" mb={2}>Nährwerte pro Portion</Text>
                  <Flex gap={4} wrap="wrap">
                    <Box>
                      <Text fontWeight="bold">Kalorien</Text>
                      <Text>{Math.round(recipe.nutrition.calories)} kcal</Text>
                    </Box>
                    <Box>
                      <Text fontWeight="bold">Protein</Text>
                      <Text>{recipe.nutrition.protein.toFixed(1)} g</Text>
                    </Box>
                    <Box>
                      <Text fontWeight="bold">Kohlenhydrate</Text>
                      <Text>{recipe.nutrition.carbs.toFixed(1)} g</Text>
                    </Box>
                    <Box>
                      <Text fontWeight="bold">Fett</Text>
                      <Text>{recipe.nutrition.fat.toFixed(1)} g</Text>
                    </Box>
                  </Flex>
                </Box>
              )}
            </Stack>
          </Box>
        </Flex>
        
        <Divider />
        
        {/* Portionen und Einkaufsliste */}
        <Flex align="center" gap={4}>
          <Text fontWeight="bold">Portionen:</Text>
          <NumberInput
            defaultValue={recipe.servings}
            min={1}
            max={20}
            w="100px"
            value={servings}
            onChange={(_, valueAsNumber) => handleServingsChange(valueAsNumber)}
          >
            <NumberInputField />
            <NumberInputStepper>
              <NumberIncrementStepper />
              <NumberDecrementStepper />
            </NumberInputStepper>
          </NumberInput>
          <Button
            leftIcon={<FaShoppingCart />}
            colorScheme="green"
            onClick={addToShoppingList}
          >
            Zur Einkaufsliste
          </Button>
        </Flex>
        
        <Divider />
        
        {/* Zutaten und Anleitung */}
        <Flex
          direction={{ base: 'column', md: 'row' }}
          gap={6}
        >
          {/* Zutaten */}
          <Box flex="1">
            <Heading as="h2" size="md" mb={4}>
              Zutaten
            </Heading>
            <List spacing={2}>
              {recipe.ingredients && recipe.ingredients.map((ingredient, index) => (
                <ListItem key={index}>
                  <Text>
                    {ingredient.amount} {ingredient.unit} {ingredient.name}
                    {ingredient.notes && <Text as="span" fontSize="sm" color="gray.600"> ({ingredient.notes})</Text>}
                  </Text>
                </ListItem>
              ))}
            </List>
          </Box>
          
          {/* Anleitung */}
          <Box flex="2">
            <Heading as="h2" size="md" mb={4}>
              Zubereitung
            </Heading>
            <Text whiteSpace="pre-line">
              {recipe.instructions}
            </Text>
          </Box>
        </Flex>
        
        {/* Notizen */}
        {recipe.notes && (
          <>
            <Divider />
            <Box>
              <Heading as="h2" size="md" mb={4}>
                Notizen
              </Heading>
              <Text whiteSpace="pre-line">
                {recipe.notes}
              </Text>
            </Box>
          </>
        )}
        
        {/* PDF-Download */}
        {recipe.pdf_path && (
          <Box mt={6}>
            <Button
              as="a"
              href={`/api/media/pdfs/${recipe.pdf_path.split('/').pop()}`}
              target="_blank"
              colorScheme="blue"
              variant="outline"
            >
              Original-PDF herunterladen
            </Button>
          </Box>
        )}
      </Stack>
    </Container>
  );
};

export default RecipeDetail;