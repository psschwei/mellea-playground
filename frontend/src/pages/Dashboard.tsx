import {
  Box,
  Grid,
  GridItem,
  Heading,
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
  Card,
  CardHeader,
  CardBody,
  Text,
  VStack,
  HStack,
  Badge,
} from '@chakra-ui/react';
import { useAuth } from '@/hooks';

export function DashboardPage() {
  const { user } = useAuth();

  return (
    <Box>
      <Heading size="lg" mb={6}>
        Welcome back, {user?.displayName}!
      </Heading>

      <Grid templateColumns="repeat(4, 1fr)" gap={6} mb={8}>
        <GridItem>
          <Card>
            <CardBody>
              <Stat>
                <StatLabel>Programs</StatLabel>
                <StatNumber>0</StatNumber>
                <StatHelpText>Total programs</StatHelpText>
              </Stat>
            </CardBody>
          </Card>
        </GridItem>

        <GridItem>
          <Card>
            <CardBody>
              <Stat>
                <StatLabel>Models</StatLabel>
                <StatNumber>0</StatNumber>
                <StatHelpText>Configured models</StatHelpText>
              </Stat>
            </CardBody>
          </Card>
        </GridItem>

        <GridItem>
          <Card>
            <CardBody>
              <Stat>
                <StatLabel>Compositions</StatLabel>
                <StatNumber>0</StatNumber>
                <StatHelpText>Visual workflows</StatHelpText>
              </Stat>
            </CardBody>
          </Card>
        </GridItem>

        <GridItem>
          <Card>
            <CardBody>
              <Stat>
                <StatLabel>Runs</StatLabel>
                <StatNumber>0</StatNumber>
                <StatHelpText>Total executions</StatHelpText>
              </Stat>
            </CardBody>
          </Card>
        </GridItem>
      </Grid>

      <Grid templateColumns="repeat(2, 1fr)" gap={6}>
        <GridItem>
          <Card>
            <CardHeader>
              <Heading size="md">Recent Activity</Heading>
            </CardHeader>
            <CardBody>
              <VStack align="stretch" spacing={3}>
                <Text color="gray.500" textAlign="center" py={4}>
                  No recent activity
                </Text>
              </VStack>
            </CardBody>
          </Card>
        </GridItem>

        <GridItem>
          <Card>
            <CardHeader>
              <Heading size="md">Quick Actions</Heading>
            </CardHeader>
            <CardBody>
              <VStack align="stretch" spacing={3}>
                <HStack justify="space-between" p={3} bg="gray.50" borderRadius="md">
                  <Text>Create a new program</Text>
                  <Badge colorScheme="blue">Coming soon</Badge>
                </HStack>
                <HStack justify="space-between" p={3} bg="gray.50" borderRadius="md">
                  <Text>Configure a model</Text>
                  <Badge colorScheme="blue">Coming soon</Badge>
                </HStack>
                <HStack justify="space-between" p={3} bg="gray.50" borderRadius="md">
                  <Text>Build a composition</Text>
                  <Badge colorScheme="blue">Coming soon</Badge>
                </HStack>
              </VStack>
            </CardBody>
          </Card>
        </GridItem>
      </Grid>
    </Box>
  );
}
